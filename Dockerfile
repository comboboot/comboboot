FROM archlinux:latest

ENV LANG="en_US.UTF-8"
RUN locale-gen en_US.UTF-8

RUN pacman -Sy --noconfirm
RUN pacman -S --noconfirm python python-aiohttp squashfs-tools zstd git make gcc p7zip

ENV COMBOSERVER=192.168.1.26:9999

RUN mkdir -p /opt/comboboot/configs
COPY ./comboserver.py /opt/comboboot/comboserver.py
COPY ./ipxebuild.sh /opt/comboboot
COPY ./static /opt/comboboot/static
RUN  /opt/comboboot/ipxebuild.sh

ENTRYPOINT ["python", "/opt/comboboot/comboserver.py" ]
