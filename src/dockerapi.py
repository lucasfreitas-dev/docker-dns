from Crypto.PublicKey import RSA
import os

import docker
import util
import config


RSA_KEY = 'Dockerfile_id_rsa'

client = docker.from_env()


NETWORK_GATEWAY = client.networks.get(
    'bridge').attrs['IPAM']['Config'][0]['Gateway']
NETWORK_SUBNET = client.networks.get(
    'bridge').attrs['IPAM']['Config'][0]['Subnet']


def get_top_level_domain(container, tld):
    return client.containers.get(
        config.DOCKER_CONTAINER_NAME).exec_run(f'sh -c "echo {config.TOP_LEVEL_DOMAIN}"').output.strip().decode("utf-8")


def check_exists(name=config.DOCKER_CONTAINER_NAME):
    try:
        return True if client.containers.get(name) else False
    except:
        return False


def purge(name=config.DOCKER_CONTAINER_NAME):
    try:
        client.api.kill(name)
    except:
        pass
    client.api.remove_container(name)


def get_exposed_port(name=config.DOCKER_CONTAINER_NAME):
    return client.containers.get(name).ports


def get_ip(name=config.DOCKER_CONTAINER_NAME):
    return client.containers.get(name).attrs['NetworkSettings']['IPAddress']


def build_container(name=config.DOCKER_CONTAINER_NAME, tag=config.DOCKER_CONTAINER_TAG, tld=config.TOP_LEVEL_DOMAIN):
    if not os.path.exists(RSA_KEY):
        print('- Creating RSA key...')
        key = RSA.generate(2048)
        with open(RSA_KEY, 'wb') as content_file:
            os.chmod(RSA_KEY, 600)
            content_file.write(key.exportKey('PEM'))
        pubkey = key.publickey()
        with open(f'{RSA_KEY}.pub', 'wb') as content_file:
            content_file.write(pubkey.exportKey('OpenSSH'))

    print('- Building...')
    client.images.build(path='.', tag=f'{tag}:latest', nocache=False)

    port_53 = 53
    if util.on_linux:
        port_53 = (NETWORK_GATEWAY, 53)

    host_config = client.api.create_host_config(
        restart_policy={'Name': 'always'},
        security_opt=['apparmor:unconfined'],
        port_bindings={
            '53/udp': port_53,
            53: port_53
        },
        publish_all_ports=True,
        binds=['/var/run/docker.sock:/var/run/docker.sock'],
    )

    client.api.create_container(tag,
                                name=name,
                                volumes=['/var/run/docker.sock'],
                                environment=[
                                    f'TOP_LEVEL_DOMAIN={tld}', f'HOSTNAME={config.HOSTNAME}', f'HOSTUNAME={config.HOSTUNAME}'],
                                #ports=['53/udp', 53],
                                host_config=host_config,
                                detach=True
                                )
    print('- Running...')
    client.api.start(name)
