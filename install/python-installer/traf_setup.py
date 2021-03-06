#!/usr/bin/env python

# @@@ START COPYRIGHT @@@
#
# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
#
# @@@ END COPYRIGHT @@@

### this script should be run on all nodes with sudo user ###

import os
import sys
import re
import json
from common import err, cmd_output, run_cmd

def run():
    dbcfgs = json.loads(dbcfgs_json)

    HOME_DIR = cmd_output('cat /etc/default/useradd |grep HOME |cut -d "=" -f 2').strip()
    TRAF_USER = dbcfgs['traf_user']
    TRAF_HOME = '%s/%s/%s-%s' % (HOME_DIR, TRAF_USER, dbcfgs['traf_basename'], dbcfgs['traf_version'])

    TRAF_VER = dbcfgs['traf_version']
    DISTRO = dbcfgs['distro']
    TRAF_LIB_PATH = TRAF_HOME + '/export/lib'
    SCRATCH_LOCS = dbcfgs['scratch_locs'].split(',')

    SUDOER_FILE = '/etc/sudoers.d/trafodion'
    SUDOER_CFG = """
## Allow trafodion id to run commands needed for backup and restore
%%%s ALL =(hbase) NOPASSWD: /usr/bin/hbase"
""" % TRAF_USER

    ### kernel settings ###
    run_cmd('sysctl -w kernel.pid_max=65535 2>&1 > /dev/null')
    run_cmd('echo "kernel.pid_max=65535" >> /etc/sysctl.conf')
    run_cmd('cp %s/sysinstall/etc/init.d/trafodion /etc/init.d' % TRAF_HOME)
    run_cmd('chkconfig --add trafodion')
    run_cmd('chkconfig --level 06 trafodion on')

    ### create and set permission for scratch file dir ###
    for loc in SCRATCH_LOCS:
        # don't set permission for HOME folder
        if not os.path.exists(loc):
            run_cmd('mkdir -p %s' % loc)
        if HOME_DIR not in loc:
            run_cmd('chmod 777 %s' % loc)

    ### copy jar files ###
    hbase_lib_path = '/usr/lib/hbase/lib'
    if 'CDH' in DISTRO:
        parcel_lib = '/opt/cloudera/parcels/CDH/lib/hbase/lib'
        if os.path.exists(parcel_lib): hbase_lib_path = parcel_lib
    elif 'HDP' in DISTRO:
        hbase_lib_path = '/usr/hdp/current/hbase-regionserver/lib'
    elif 'APACHE' in DISTRO:
        hbase_home = dbcfgs['hbase_home']
        hbase_lib_path = hbase_home + '/lib'
        # for apache distro, get hbase version from cmdline
        hbase_ver = cmd_output('%s/bin/hbase version | head -n1' % hbase_home)
        hbase_ver = re.search(r'HBase (\d\.\d)', hbase_ver).groups()[0]
        DISTRO += hbase_ver

    distro, v1, v2 = re.search(r'(\w+)-*(\d)\.(\d)', DISTRO).groups()
    if distro == 'CDH':
        if v2 == '6': v2 = '5'
        if v2 == '8': v2 = '7'
    elif distro == 'HDP':
        if v2 == '4': v2 = '3'

    hbase_trx_jar = 'hbase-trx-%s%s_%s-%s.jar' % (distro.lower(), v1, v2, TRAF_VER)
    traf_hbase_trx_path = '%s/%s' % (TRAF_LIB_PATH, hbase_trx_jar)
    hbase_trx_path = '%s/%s' % (hbase_lib_path, hbase_trx_jar)
    if not os.path.exists(traf_hbase_trx_path):
        err('Cannot find HBase trx jar \'%s\' for your Hadoop distribution' % hbase_trx_jar)

    # upgrade mode, check if existing trx jar doesn't match the new trx jar file
    if dbcfgs.has_key('upgrade') and dbcfgs['upgrade'].upper() == 'Y':
        if not os.path.exists(hbase_trx_path):
            err('The trx jar \'%s\' doesn\'t exist in hbase lib path, cannot do upgrade, please do regular install' % hbase_trx_jar)
    else:
        # remove old trx and trafodion-utility jar files
        run_cmd('rm -rf %s/{hbase-trx-*,trafodion-utility-*}' % hbase_lib_path)

        # copy new ones
        run_cmd('cp %s %s' % (traf_hbase_trx_path, hbase_lib_path))
        run_cmd('cp %s/trafodion-utility-* %s' % (TRAF_LIB_PATH, hbase_lib_path))

    # set permission
    run_cmd('chmod +r %s/{hbase-trx-*,trafodion-utility-*}' % hbase_lib_path)

    if dbcfgs['dcs_ha'] == 'Y':
        # set trafodion sudoer file for specific cmds
        SUDOER_CFG += """
## Trafodion Floating IP commands
Cmnd_Alias IP = /sbin/ip
Cmnd_Alias ARP = /sbin/arping

## Allow Trafodion id to run commands needed to configure floating IP
%%%s ALL = NOPASSWD: IP, ARP
""" % TRAF_USER

    ### write trafodion sudoer file ###
    with open(SUDOER_FILE, 'w') as f:
        f.write(SUDOER_CFG)

# main
try:
    dbcfgs_json = sys.argv[1]
except IndexError:
    err('No db config found')
run()
