
1) configure server dhcp to boot with ipxe script

Openwrt dnsmasq configuration when comboserver is at 192.168.1.10

uci del dhcp.linux
uci set dhcp.linux=boot
uci set dhcp.linux.serveraddress='192.168.1.10'
uci set dhcp.linux.filename='comboboot.pxe'
uci set dhcp.linux.servername='192.168.1.10'
uci commit
/etc/init.d/dnsmasq restart


2) ipxe with embedded boot script created via ./ipxebuild.sh
   ipxe boot the system via tftp/http communicating with comboserver.py

3) 
