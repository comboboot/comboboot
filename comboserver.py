#!/usr/bin/env python

import asyncio
import os
import io
import time

import struct
import socket
import subprocess
import socket
from aiohttp import web

COMBOSERVER_IP, COMBOSERVER_PORT = os.environ.get("COMBOSERVER", "127.0.0.1:9999").split(":")


COMBODIR=(os.path.dirname(os.path.abspath(__file__)))

IPXE_ITEMS=[("arch_install","arch install", """
kernel http://{WEBBASE}/iso/arch-install/arch/boot/x86_64/vmlinuz-linux archisobasedir=arch archiso_http_srv=http://{WEBBASE}/iso/arch-install/ ip=dhcp script=http://{WEBBASE}/static/comboboot_sfxgen.sh.cgi
initrd http://{WEBBASE}/iso/arch-install/arch/boot/x86_64/initramfs-linux.img
""")]

class ClientSession:
    def __init__(self, WEBIP, WEBPORT):
        self.tftptransfers = {}
        self.uuid = None
        self.WEBIP = WEBIP
        self.WEBPORT = WEBPORT

    def WEBSESSION(self):
        return "%s:%s/%s/" % (self.WEBIP, self.WEBPORT, self.uuid)

    def WEBBASE(self):
        return "%s:%s" % (self.WEBIP, self.WEBPORT)

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

    def get_cfg(self):
        import copy
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
        if self.uuid=="iso":
            if tail.startswith("arch-install/"):
                tail = tail.replace("arch-install/", "", 1)
                isoPath = os.path.join(self.configsdir, "default", "archlinux-2022.11.01-x86_64.iso")
                cmd = ["7z", "x", "-so", isoPath, tail]
                #TODO: convert to stream...
                output = subprocess.check_output(cmd)
                print(" ".join(cmd), len(output))

                resp = web.StreamResponse()
                resp.content_type = "text/plain"
                await resp.prepare(request)
                await resp.write(output)
                return resp

        if self.uuid=="static":
            f = os.path.join(COMBODIR, "static", tail)
            if tail.endswith(".cgi"):
                f = f.replace(".cgi", "")
                f = subprocess.check_output([f], stderr=None)

                resp = web.StreamResponse()
                resp.content_type = "text/plain"
                await resp.prepare(request)
                await resp.write(f)
                return resp

        if tail.endswith("cfg"):
            resp = web.StreamResponse()
            resp.content_type = "text/plain"
            await resp.prepare(request)
            await resp.write(self.get_cfg().read())
            return resp

        return web.FileResponse(f)

    async def handle_post(self, request):
        # TODO: fix ugly way of detectig if we're sending tar stream
        fpath = os.path.join(self.get_machine_dir(), "new")
        fpath_target = os.path.join(self.get_machine_dir(), f"{int(time.time())}")
        if "Content-Type" not in request.headers:
            import shutil
            os.makedirs(fpath, exist_ok=True)
            from subprocess import Popen, PIPE, STDOUT
            if os.path.exists(os.path.join(fpath, "rootfs.squashfs.new")):
                os.unlink(os.path.join(fpath, "rootfs.squashfs.new"))
            # -b 1048576 -comp zstd -Xcompression-level 22
            p = Popen(["bash", "-c", "zstdcat - | sqfstar -b 1048576 -comp zstd  new/rootfs.squashfs.new"], stdout=None, stdin=PIPE, stderr=None, cwd=self.get_machine_dir())
            while True:
                chunk = await request.content.readany()
                if not chunk:
                    break
                p.stdin.write(chunk)
            p.stdin.close()
            p.wait()
            os.rename(os.path.join(fpath, "rootfs.squashfs.new"), os.path.join(fpath, "rootfs.squashfs"))
            return web.Response()

        reader = await request.multipart()
        while True:
            part = await reader.next()
            if part is None:
                os.rename(fpath, fpath_target)
                break
            fpath_tg = os.path.join(fpath, part.name)
            print("writing", fpath_tg)
            os.makedirs(os.path.dirname(fpath_tg), exist_ok=True)
            f = open(fpath_tg, "wb")
            while not part.at_eof():
                filedata = await part.read_chunk()
                f.write(filedata)
        resp = web.Response()
        return resp

    def get_machine_dir(self):
        return self.configsdir + "/" + self.uuid

    def handle_ipxe_cfg(self, filename):
        uuid = filename.strip("/").replace("arch/pxelinux.cfg/", "")
        self.uuid = uuid

        return self.get_cfg()


class TftpPxe:
    """ serves tftp connections from ipxe clients
    pxe requests via tftp also initiates the session
    """

    current_clients = {}

    async def handle(self, request):
        """ asyncio handler for http request """
        session = self.findSessionByRequest(request)
        return await session.handle_http(request)

    async def handle_post(self, request):
        session = self.findSessionByRequest(request)
        return await session.handle_post(request)

    def startSession(self, host):
        # TODO: add timeout for session
        WEBPORT = self.WEBPORT
        WEBIP = COMBOSERVER_IP
        session = ClientSession(WEBIP, WEBPORT)
        session.configsdir = os.path.join(COMBODIR, "configs")
        self.current_clients[host] = session
        return session

    def stopSession(self, host):
        del self.current_clients[host]

    def findSessionByHost(self, host):
        return self.current_clients[host]

    def findSessionByRequest(self, request):
        uuid = request.match_info.get('uuid')
        for x in self.current_clients.values():
            if x.uuid == uuid:
                return x

        remote = request.remote
        session = self.startSession(remote)
        session.uuid = uuid
        return session

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
            session = self.startSession(host)
            session.tftp_send_file(self.transport, f, host_port)
        elif "arch/pxelinux.cfg" in filename:
            session = self.startSession(host)
            f = session.handle_ipxe_cfg(filename)
            session.tftp_send_file(self.transport, f, host_port)
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

        sock = self.transport.get_extra_info('socket')
        if tftpOpcode == 1:
            self.handle_RRQ(data, host_port)
        elif tftpOpcode == 4:
            new_block = struct.unpack("!h", data[2:4])[0]
            self.findSessionByHost(host).tftp_send_chunk(self.transport, new_block + 1, host_port)
        elif tftpOpcode == 5:
            ERROR_str = data[2:].decode()
            # on error remove transfer
            self.findSessionByHost(host).tftp_stop_file(host_port)


async def main():
    loop = asyncio.get_running_loop()
    exit_future = asyncio.Future(loop=loop)

    tftp_transport, tftp_protocol = await loop.create_datagram_endpoint(lambda: TftpPxe(), local_addr=('0.0.0.0', 69))

    app = web.Application()
    app.add_routes([web.get('/{uuid}/{tail:.*}', lambda request: tftp_protocol.handle(request))])
    app.add_routes([web.post('/{uuid}/{tail:.*}', lambda request: tftp_protocol.handle_post(request))])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, port=COMBOSERVER_PORT)
    await site.start()

    for x in site._server.sockets:
        if x.family == socket.AddressFamily.AF_INET:
            tftp_protocol.WEBPORT = x.getsockname()[1]

    try:
        await exit_future
    finally:
        tftp_transport.close()

asyncio.run(main())
