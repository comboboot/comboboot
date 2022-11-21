#!/usr/bin/env python

import asyncio
import os
import io
import time
import copy

import struct
import socket
import subprocess
import socket
from aiohttp import web

from concurrent.futures import ThreadPoolExecutor

COMBOSERVER_IP, COMBOSERVER_PORT = os.environ.get("COMBOSERVER", "127.0.0.1:9999").split(":")
COMBODIR=(os.path.dirname(os.path.abspath(__file__)))

IPXE_ITEMS=[("arch_install","Archlinux installation", """
kernel http://{WEBBASE}/iso/arch-install/arch/boot/x86_64/vmlinuz-linux archisobasedir=arch archiso_http_srv=http://{WEBBASE}/iso/arch-install/ ip=dhcp script=http://{WEBBASE}/static/comboboot_sfxgen.sh.cgi
initrd http://{WEBBASE}/iso/arch-install/arch/boot/x86_64/initramfs-linux.img
""")]

class ClientSession:
    def __init__(self, uuid):
        self.uuid = uuid

    def WEBSESSION(self):
        return "%s:%s/%s/" % (COMBOSERVER_IP, COMBOSERVER_PORT, self.uuid)

    def WEBBASE(self):
        return "%s:%s" % (COMBOSERVER_IP, COMBOSERVER_PORT)

    def gen_ipxe_cfg(self, request):
        #TODO: cleanup pxe menu generation
        pxe_items = copy.deepcopy(IPXE_ITEMS)
        if os.path.exists(self.get_machine_dir()):
            for x in os.listdir((self.get_machine_dir())):
                cfgFilePath = os.path.join(self.get_machine_dir(), x, "cfg")
                if os.path.exists(cfgFilePath):
                    item_cfg =""
                    for y in open(os.path.join(cfgFilePath)).read().strip().split("\n"):
                        if y.startswith("kernel") or y.startswith("initrd"):
                            item_cfg += y+"\n"
                else:
                    item_cfg = """
kernel http://{WEBSESSION}/vmlinuz-linux ip=dhcp squashfs=http://{WEBSESSION}/rootfs.squashfs initrd=amd-ucode.img initrd=initramfs-linux
initrd http://{WEBSESSION}/amd-ucode.img
initrd http://{WEBSESSION}/initramfs-linux.img
"""
                item_cfg = item_cfg.replace("{WEBBASE}", self.WEBBASE()+x)
                item_cfg = item_cfg.replace("{WEBSESSION}", self.WEBSESSION()+x)
                pxe_items.insert(0, (x ,x, item_cfg))

        cfg_boot = ""
        cfg = """#!ipxe

:menu
menu shim transparent loader demo
"""
        for inst,name,cont in pxe_items:
            inst+="_name"
            cfg += f"item {inst} {name}\n"
            cfg_boot += "\n"
            cfg_boot += f":{inst}\n"
            cfg_boot += cont
            cfg_boot += """
boot
"""
        cfg +="""
item shell         iPXE internal shell
item exit          Exit
choose option && goto ${option}
"""

        cfg += cfg_boot
        cfg +=""":shell
shell ||
goto menu

:exit
exit

"""
        cfg = cfg.replace("{WEBBASE}", self.WEBBASE())
        cfg = cfg.replace("{WEBSESSION}", self.WEBSESSION())
        f = io.BytesIO(cfg.encode())
        return f

    async def handle_http(self, request):
        tail = request.match_info.get('tail', "")
        print(f"handle_http {self.uuid} {tail}", request.url)
        f = self.get_machine_dir() + "/" + tail

        if tail.endswith("cfg"):
            resp = web.StreamResponse()
            resp.content_type = "text/plain"
            await resp.prepare(request)
            await resp.write(self.gen_ipxe_cfg(request).read())
            return resp

        return web.FileResponse(f)

    async def handle_post(self, request):
        from datetime import datetime
        now = datetime.now()
        cfg_name = now.strftime("%m%d%Y_%H%M")

        machine_path = os.path.join(self.get_machine_dir(), f"{cfg_name}")
        machine_path_tmp = machine_path+"_tmp"
        os.makedirs(machine_path_tmp)



        reader = await request.multipart()
        while True:
            part = await reader.next()
            if part is None:
                if os.path.exists(f"{machine_path_tmp}/rootfs.tar.zst"):
                    repack_cmd = "zstdcat rootfs.tar.zst | sqfstar -force -b 1048576 -comp zstd rootfs.squashfs"
                    subprocess.check_call(["bash", "-c", repack_cmd], cwd=machine_path_tmp)
                os.rename(machine_path_tmp, machine_path)
                break
            print("writing", part.name)
            with open(os.path.join(machine_path_tmp, part.name), "wb") as f:
                while not part.at_eof():
                    filedata = await part.read_chunk()
                    f.write(filedata)

        resp = web.StreamResponse()
        resp.content_type = "text/plain"
        await resp.prepare(request)
        await resp.write(f"configuration {cfg_name} created\n".encode())
        return resp

    def get_machine_dir(self):
        return os.path.join(COMBODIR, "configs", self.uuid)

class Comboserver:
    """ serves tftp connections from ipxe clients
    pxe requests via tftp also initiates the session
    """

    def __init__(self):
        pass

    async def handle(self, request):
        """ asyncio handler for http request """
        session = self.findSessionByRequest(request)
        return await session.handle_http(request)

    async def handle_iso(self, request):
        tail = request.match_info.get('tail', "")
        if tail.startswith("arch-install/"):
            tail = tail.replace("arch-install/", "", 1)
            isoPath = os.path.join(COMBODIR, "configs", "default", "archlinux-2022.11.01-x86_64.iso")
            cmd = ["7z", "x", "-so", isoPath, tail]
            #TODO: convert to stream...
            output = subprocess.check_output(cmd)
            print(" ".join(cmd), len(output))

            resp = web.StreamResponse()
            resp.content_type = "text/plain"
            await resp.prepare(request)
            await resp.write(output)
            return resp

    async def handle_static(self, request):
        tail = request.match_info.get('tail', "")
        f = os.path.join(COMBODIR, "static", tail)
        if tail.endswith(".cgi"):
            f = f.replace(".cgi", "")
            f = subprocess.check_output([f], stderr=None)

            resp = web.StreamResponse()
            resp.content_type = "text/plain"
            await resp.prepare(request)
            await resp.write(f)
            return resp

    async def handle_post(self, request):
        session = self.findSessionByRequest(request)
        return await session.handle_post(request)

    def findSessionByRequest(self, request):
        uuid = request.match_info.get('uuid')
        return ClientSession(uuid)

class ComboserverTFTP:
    def __init__(self):
        # TODO: timeout transfers
        self.tftptransfers = {}

    def tftp_get_chunk(self, block_number, host_port, blksize=512):
        f = self.tftptransfers[host_port]
        if f.eof_custom_mark:
            self.tftp_stop_file(host_port)
            return bytes()
        seek = (block_number-1)*blksize
        if f.tell() != seek:
            f.seek(seek)
        data = f.read(blksize)
        if len(data) != blksize:
            f.eof_custom_mark = True
        return data

    def tftp_send_chunk(self, transport, block_number, host_port):
        data_chunk = self.tftp_get_chunk(block_number, host_port)
        CMD = 3
        data_write = struct.pack("!hh", CMD, block_number) + data_chunk
        transport.sendto(data_write, host_port)

    def tftp_send_file(self, transport, f, host_port):
        self.tftptransfers[host_port] = f
        f.eof_custom_mark = False
        self.tftp_send_chunk(transport, 1, host_port)

    def tftp_stop_file(self, host_port):
        del self.tftptransfers[host_port]

    def handle_RRQ(self, data, host_port):
        """ handle tfrp request """

        host, port = host_port
        x = data[2:].split(b'\x00')
        filename = x[0].decode()
        mode = x[1].decode().lower()
        assert(mode == "octet")

        if filename == "comboboot.pxe":
            # redirect default entry into pxe boot
            filename = os.path.join(COMBODIR, "comboboot.pxe")
            f = open(filename, 'rb')
            self.tftp_send_file(self.transport, f, host_port)
        else:
            print("unknown file ", filename)

    def connection_made(self, transport):
        """ asyncio handler for tftp"""
        # transport will be used to sent outgoing requests
        self.transport = transport

    def datagram_received(self, data, host_port):
        """ asyncio handler for tftp """
        tftpOpcode = struct.unpack("!h", data[:2])[0]
        host, port = host_port

        if tftpOpcode == 1:
            self.handle_RRQ(data, host_port)
        elif tftpOpcode == 4:
            new_block = struct.unpack("!h", data[2:4])[0]
            self.tftp_send_chunk(self.transport, new_block + 1, host_port)
        elif tftpOpcode == 5:
            ERROR_str = data[2:].decode()
            # on error remove transfer
            self.tftp_stop_file(host_port)

async def main():
    loop = asyncio.get_running_loop()
    exit_future = asyncio.Future(loop=loop)

    tftp_transport, tftp_protocol = await loop.create_datagram_endpoint(lambda: ComboserverTFTP(), local_addr=('0.0.0.0', 69))

    comboserver = Comboserver()

    app = web.Application()
    app.add_routes([web.get('/iso/{tail:.*}', lambda request: comboserver.handle_iso(request))])
    app.add_routes([web.get('/static/{tail:.*}', lambda request: comboserver.handle_static(request))])
    app.add_routes([web.get('/{uuid}/{tail:.*}', lambda request: comboserver.handle(request))])
    app.add_routes([web.post('/{uuid}/{tail:.*}', lambda request: comboserver.handle_post(request))])
    app["executor"] = ThreadPoolExecutor(max_workers=5)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=COMBOSERVER_PORT)
    await site.start()

    try:
        await exit_future
    finally:
        tftp_transport.close()

asyncio.run(main())
