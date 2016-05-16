#!/usr/bin/python

import json
import os
import shlex
import shutil
import spur
from docker import Client

APPS = [
    ('git@github.com:Vauxoo/yoytec.git', 'yoytec'),
    ('git@github.com:Vauxoo/yoytec.git', 'erp_vauxoo_com'),
    ('git@github.com:Vauxoo/lodigroup.git', 'lodi'),
    ('git@github.com:Vauxoo/lodigroup.git', 'apex'),
    ('git@github.com:Vauxoo/lodigroup.git', 'exim'),
    ('git@github.com:Vauxoo/ever.git', 'ever')
]

BASE_IMAGE = 'vauxoo/odoo-80-image'
DB_USER = 'truiz'
DB_PASSWORD = 'truiz'

def makedir(path_name):
    try:
        os.mkdir(path_name)
    except OSError as error:
        if 'File exists' not in error.strerror:
            raise


def clone_repo(repo, path):
    try:
        shell.run(
            shlex.split('git clone -b 8.0 --single-branch --depth=1 {repo} {path}'.format(
                repo=repo,
                path=path)))
    except spur.results.RunProcessError as error:
        if 'already exists and is not an empty directory' not in error.stderr_output:
            raise


def clean_dbs(app_name):
    shell.run(shlex.split('psql -c "DROP DATABASE IF EXISTS {app}_install" postgres'
                          .format(app=app_name)))

    shell.run(shlex.split('psql -c "DROP DATABASE IF EXISTS {app}_test" postgres'
                          .format(app=app_name)))
    shell.run(shlex.split('psql -c "CREATE DATABASE {app}_install" postgres'
                          .format(app=app_name)))
    shell.run(shlex.split('psql -c "CREATE DATABASE {app}_test" postgres'
                          .format(app=app_name)))


def start_container(app_name, container_name):
    compose_file = """
odoo80:
  ports:
    - "8069"
    - "8072"
  image: {app}80
  container_name: {name}
  hostname: test_{app}80
  command: "/entry_point.py"
  mem_limit: "1024MB"
  environment:
    - DB_HOST=172.17.0.1
    - DBFILTER=.*
    - ODOO_CONFIG_FILE=/home/odoo/.openerp_serverrc
    - DB_USER={db_user}
    - DB_PASSWORD={db_pass}
    - ADMIN_PASSWD=KtCY
    - ODOO_USER=odoo
        """.format(
        app=app_name,
        name=container_name,
        db_user=DB_USER,
        db_pass=DB_PASSWORD
    )

    with open("docker-compose.yml", "w") as text_file:
        text_file.write(compose_file)
    shell.run(['docker-compose', 'up', '-d'])


def install_app(container_name, app_name):
    exec_id = cli.exec_create(
        container_name,
        '/home/odoo/instance/odoo/odoo.py -d {app}_install -i {app} --stop-after-init --without-demo=all'
        .format(app=app_name),
        user='odoo'
    )
    for line in cli.exec_start(exec_id, stream=True):
        print line.strip()


def test_app(container_name, app_name):
    exec_id = cli.exec_create(
        container_name,
        '/home/odoo/instance/odoo/odoo.py -d {app}_install -i {app} --stop-after-init --test-enable --log-level=test'
        .format(app=app_name),
        user='odoo'
    )
    for line in cli.exec_start(exec_id, stream=True):
        print line.strip()


if __name__ == '__main__':
    makedir('files')
    shell = spur.LocalShell()
    clone_repo('https://github.com/Vauxoo/odoo.git', 'odoo')
    cli = Client()

    for app in APPS:
        working_path = os.path.join('files', app[1])
        instance_path = os.path.join(working_path, 'instance')
        extra_path = os.path.join(instance_path, 'extra_addons')
        makedir(working_path)
        makedir(instance_path)
        makedir(extra_path)
        print 'Building instance for: {app}'.format(app=app[1])
        try:
            shutil.copytree('odoo', os.path.join(instance_path, 'odoo'))
        except OSError as error:
            if 'File exists' not in error.strerror:
                raise
        clone_repo(app[0], os.path.join(extra_path, app[1]))
        shell.run(shlex.split('./clone_oca_dependencies {path} {path}'.format(path=extra_path)))

        docker_file = """
FROM {image}

COPY files/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY files/openerp_serverrc /external_files/openerp_serverrc
COPY files/{app}/instance /home/odoo/instance
COPY files/openerp_serverrc /home/odoo/.openerp_serverrc
COPY files/install_deps.sh /home/odoo/install_deps.sh
RUN  bash /home/odoo/install_deps.sh

USER odoo
ENV HOME="/home/odoo" \\
    ODOO_CONFIG_FILE="/home/odoo/.openerp_serverrc" \\
    ODOO_FILESTORE_PATH="/home/odoo/.local/share/Odoo/filestore" \\
    XDG_DATA_HOME="/home/odoo/.local/share" \\
    VERSION="8.0"

USER root

## The volumes we want to use
VOLUME ["/var/log/supervisor", "/home/odoo/.local/share/Odoo", "/tmp", "/home/odoo/.ssh"]

## Expose xmlrpc and longpolling ports
EXPOSE 8069 8072
CMD /entry_point.py
        """.format(
            image=BASE_IMAGE,
            app=app[1]
        )
        with open('Dockerfile', 'w') as text_file:
            text_file.write(docker_file)
        print 'Building image'
        for line in cli.build(path='.', rm=True, tag='{app}80'.format(app=app[1]), timeout=3600):
            obj = json.loads(line)
            print obj.get('stream').strip()

        container_name = 'test_{app}80'.format(app=app[1])
        clean_dbs(app[1])
        start_container(app[1], container_name)
        print 'Stop odoo instance'
        exec_id = cli.exec_create(container_name, 'supervisorctl stop odoo')
        cli.exec_start(exec_id)
        print 'Install app'
        install_app(container_name, app[1])
        print 'Test app'
        test_app(container_name, app[1])
