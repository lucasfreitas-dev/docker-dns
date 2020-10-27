import os
import shutil
import time

import config
import dockerapi as docker
import util
import network
import tunnel

DOCKER_CONF_FOLDER = '/etc/docker'
DNSMASQ_LOCAL_CONF = '/etc/NetworkManager/dnsmasq.d/01_docker'
KNOWN_HOSTS_FILE = f'{config.HOME_ROOT}/.ssh/known_hosts'
WSL_CONF = '/etc/wsl.conf'
DNS = '127.0.0.1'
DISABLE_MAIN_RESOLVCONF_ROUTINE = True
RESOLVCONF = '/var/run/resolvconf/resolv.conf'
RESOLVCONF_HEADER = 'options timeout:1 #@docker-dns\nnameserver 127.0.0.1 #@docker-dns'

if not os.path.exists(DNSMASQ_LOCAL_CONF):
    DNSMASQ_LOCAL_CONF = DNSMASQ_LOCAL_CONF.replace('dnsmasq.d', 'conf.d')


def __generate_resolveconf():
    RESOLVCONF_DATA = open(RESOLVCONF, 'r').read()

    RESOLVCONF_DATA = f"{RESOLVCONF_HEADER}\n{RESOLVCONF_DATA}"
    open(RESOLVCONF, 'w').write(RESOLVCONF_DATA)

    resolv_script = f"""#!/usr/bin/env sh
rm /etc/resovl.conf;
echo "{RESOLVCONF_HEADER}\n" > /etc/resolv.conf
cat ${RESOLVCONF} >> /etc/resolv.conf
"""
    open(f'{config.BASE_PATH}/bin/docker-dns.service.sh',
         'w').write(resolv_script)
    os.chmod(f'{config.BASE_PATH}/bin/docker-dns.service.sh', 0o744)

    service_script = f"""[Unit]
After=network.service

[Service]
ExecStart={config.BASE_PATH}/bin/docker-dns.service.sh

[Install]
WantedBy=default.target"""
    open('/etc/systemd/system/docker-dns.service', 'w').write(service_script)
    os.chmod('/etc/systemd/system/docker-dns.service', 0o664)

    os.system('sudo systemctl daemon-reload > /dev/null')
    os.system('sudo systemctl enable docker-dns.service > /dev/null')


def __get_windows_username():
    return os.popen(
        "powershell.exe '$env:UserName'").read().split('\n')[0]


def __generate_powershellbat(tld=None):
    if not tld:
        return False

    script = f"""
@echo "Enable DNS for top level domain "{tld}"    
Add-DnsClientNrptRule -Namespace "{tld}" -NameServers "127.0.0.1"
"""

    WINDOWS_USER = __get_windows_username()
    open(
        f'/mnt/c/Users/{WINDOWS_USER}/Desktop/docker-dns.bat', 'w').write(script)
    os.system(
        f'powershell.exec /mnt/c/Users/{WINDOWS_USER}/Desktop/docker-dns.bat')


def setup(tld=config.TOP_LEVEL_DOMAIN):
    if not os.path.isdir('/etc/resolver'):
        os.mkdir('/etc/resolver')
    open(f'/etc/resolver/{tld}',
         'w').write(f'nameserver 127.0.0.1')

    # DO NOT DISABLE WSL RESOLV.CONF GENARATION!!! IT WILL BREAK LINUX FOR NOW
    #
    #ini = ''
    # if os.path.exists(WSL_CONF):
    #    ini = open(WSL_CONF, 'r').read()

    # if '[network]' not in ini:
    #    ini += "\n[network]\ngenerateResolvConf = false\n"
    # else:
    #    if 'generateResolvConf' not in ini:
    #        ini = ini.replace('[network]', "[network]\ngenerateResolvConf = false\n")
    #    else:
    #        ini = ini.split("\n")
    #        i = 0
    #        for line in ini:
    #            if 'generateResolvConf' in line:
    #                ini[i] = "generateResolvConf = false\n"
    #                break
    #            i += 1
    #        ini = "\n".join(ini)
    #open(WSL_CONF, 'w').write(ini)

    return True


def install(tld=config.TOP_LEVEL_DOMAIN):
    print('Generating known_hosts backup for user "root", if necessary')
    if not os.path.exists(f'{config.HOME_ROOT}/.ssh'):
        os.mkdir(f'{config.HOME_ROOT}/.ssh')
        os.chmod(f'{config.HOME_ROOT}/.ssh', 700)

    if os.path.exists(KNOWN_HOSTS_FILE):
        shutil.copy2(KNOWN_HOSTS_FILE,
                     f'{config.HOME_ROOT}/.ssh/known_hosts_pre_docker-dns')

    time.sleep(3)
    port = False
    ports = docker.get_exposed_port(config.DOCKER_CONTAINER_NAME)
    if '22/tcp' in ports:
        port = int(ports['22/tcp'][0]['HostPort'])
    if not port:
        raise('Problem fetching ssh port')

    os.system(
        f'ssh-keyscan -H -t ecdsa-sha2-nistp256 -p {port} 127.0.0.1 2> /dev/null >> {KNOWN_HOSTS_FILE}')

    # Running the powershell bat script makes the resolvconf generation OBSOLETE
    # __generate_resolveconf()

    __generate_powershellbat(tld=tld)

    # create etc/resolv.conf for
    return True


def uninstall(tld=config.TOP_LEVEL_DOMAIN):
    if os.path.exists(f'/etc/resolver/{tld}'):
        print('Removing resolver file')
        os.unlink(f'/etc/resolver/{tld}')

    ini = open(WSL_CONF, 'r').read()
    ini = ini.replace('ngenerateResolvConf = false',
                      'ngenerateResolvConf = true')
    open(WSL_CONF, 'w').write(ini)

    if os.path.exists(DNSMASQ_LOCAL_CONF):
        os.unlink(DNSMASQ_LOCAL_CONF)

    if os.path.exists(f'{config.HOME_ROOT}/.ssh/known_hosts_pre_docker-dns'):
        print('Removing kwown_hosts backup')
        os.unlink(f'{config.HOME_ROOT}/.ssh/known_hosts_pre_docker-dns')

    WINDOWS_USER = __get_windows_username()
    if os.path.exists(f'/mnt/c/Users/{WINDOWS_USER}/Desktop/docker-dns.bat'):
        print('Removing bat file from Windows Desktop')
        os.unlink(f'/mnt/c/Users/{WINDOWS_USER}/Desktop/docker-dns.bat')
