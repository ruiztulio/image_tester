#!/usr/bin/env bash

function create_user(){
    adduser --home=/home/odoo --disabled-password --gecos "" --shell=/bin/bash odoo
    echo 'root:odoo' | chpasswd
    mkdir -p /home/odoo/.ssh
    mkdir -p /home/odoo/.local/share

    ## Scan the keys to avoid the add question
    ssh-keyscan github.com > /home/odoo/.ssh/known_hosts
}

function entry_point(){
    mkdir -p /external_files
    wget -q -O /entry_point.py https://raw.githubusercontent.com/vauxoo/docker_entrypoint/master/entry_point.py
    chmod +x /entry_point.py
}

create_user
entry_point

mkdir -p /var/log/supervisor
git clone -b master https://github.com/OCA/maintainer-quality-tools /tmp/mqt
find /home/odoo/instance -type f -name requirements.txt -exec sh -c "pip install -r \"{}\"" \;
ADDONS="$(python /tmp/mqt/travis/getaddons.py /home/odoo/instance/extra_addons)"
sed -ri "s%(addons_path).*$%\1 = /home/odoo/instance/odoo/addons,${ADDONS}%g" /home/odoo/.openerp_serverrc

# Cleanup
rm -rf /tmp/*
chown -R odoo:odoo /home/odoo
