from fabric.api import *
from fabric.contrib.files import upload_template
import cuisine
import pickle
import time
import hashlib
import os

env.user = "root"
env.hosts = [
    #"hoyga.com",
    "178.79.166.35",
]

def cuisine_sudo(fn):
    def __inner__(*args, **kwargs):
        with cuisine.mode_sudo():
            return fn(*args, **kwargs)
    return __inner__

def set_config(key, val):
    cuisine.dir_ensure("/etc/installconfig")
    filename = "/etc/installconfig/%s.pk" % key
    cuisine.file_write(filename, pickle.dumps(val))

def get_config(key, default=None):
    filename = "/etc/installconfig/%s.pk" % key
    if cuisine.file_exists(filename):
        return pickle.loads(cuisine.file_read(filename))
    else:
        return default

def once(key):
    if not get_config("once_%s" % key, False):
        set_config("once_%s" % key, True)
        return True
    return False

def md5(s):
    return hashlib.md5(s).hexdigest()

@cuisine_sudo
def install_packages():
    packages = """
        python-setuptools
        git-core
        apache2
        libapache2-mod-php5
        libapache2-mod-wsgi
        mysql-server
        mysql-client
        php-pear
        php5
        php5-cli
        php5-curl
        php5-mysql
        php5-tidy
        php5-curl
        wget
        curl
        git
        htop
        aptitude
    """.split()
    sudo('echo "mysql-server-5.5 mysql-server/root_password password ape" | debconf-set-selections')
    sudo('echo "mysql-server-5.5 mysql-server/root_password_again password ape" | debconf-set-selections')

    if (time.time() - get_config("packages_updated", 0)) > 7*24*60*60:
        set_config("package_updated", time.time())
        cuisine.package_update()

    for package in packages:
        cuisine.package_ensure(package)

    if once("pip"):
        sudo('easy_install pip')

    if once("cache_lite"):
        sudo('pear install Cache_Lite')

dbs = "eureka", "foursquare", "hoyga", "poi"
def setup_databases():
    sql = []
    for db in dbs:
        sql.append("CREATE DATABASE IF NOT EXISTS %s;" % db)
        sql.append("GRANT ALL ON %s.* TO '%s'@'localhost';" % (db, db))
    tmp = cuisine.tempfile.mktemp()
    cuisine.file_write(tmp, sql)
    run("mysql -u root -pape < %s" % tmp)
    run("rm %s" % tmp)

def backup_databases():
    tmp = cuisine.tempfile.mktemp()
    for db in dbs:
        run("mysqldump -u root -pape %s > %s" % (db, tmp))
        filename = "../backups/%s-%s.sql" % (db, time.strftime('%Y%m%d%H%M%S'))
        get(tmp, filename)
        local("ln -s '%s' '../backups/%s-latest.sql'" % (filename, db))

def restore_databases():
    tmp = cuisine.tempfile.mktemp()
    for db in dbs:
        put("../backups/%s-latest.sql" % db, tmp)
        run("mysql -u root -pape %s < %s" % (db, tmp))
    run("rm %s" % tmp)

file_dirs = (
    "/var/www/4sq",
    "/var/www/hoyga",
    "/var/www/git",
    "/var/www/eureka",
    "/var/www/cernpoi",
    "/var/www/brweb",
    "/var/www/bengoa",
    "/var/django/bugtracker",
    "/var/django/comand",
    "/var/git"
)

def backup():
    for file_dir in file_dirs:
        filename = "../backups/%s.tar.gz" % md5(file_dir)
        if not os.path.exists(filename):
            tmp = cuisine.tempfile.mktemp()
            run("tar -zcf '%s' '%s'" % (tmp, file_dir))
            get(tmp, filename)
            run("rm '%s'" % tmp)

def restore():
    with cd("/"):
        for file_dir in file_dirs:
            filename = "../backups/%s.tar.gz" % md5(file_dir)
            if not os.path.exists(filename):
                print "WARNING: Doesn't exits %s" % filename
                continue
            tmp = cuisine.tempfile.mktemp()
            put(filename, tmp)
            run("tar -zxf '%s'" % (tmp))
            run("rm '%s'" % tmp)

repos = (
    ("https://github.com/YouWoTMA/cernpoi.git", "master", "/var/www/cernpoi/"),
)

def clone_repos():
    for url, branch, path in repos:
        if not cuisine.file_exists(path):
            sudo("git clone '%s' '%s'" % (url, path))
            with cd(path):
                sudo("git checkout %s" % branch)

@cuisine_sudo
def setup_vhosts():
    simple_vhosts = (
        ("bengoa", "bengoa.co.uk", "bengoa.com"),
        ("cernpoi", "cerntourism.dvdbng.com"),
        ("4sq", "4sq.dvdbng.com"),
        ("eureka", "redeureka.es"),
        ("hoyga", "hoyga.com"),
        ("brweb", "bengoarocandio.com", "dvdbng.com"),
        ("brweb/david", "david.bengoarocandio.com"),
    )
    for vhost in simple_vhosts:
        name, domains = vhost[0], vhost[1:]
        main_domain = domains[0]
        alias = list(domains[1:])
        for domain in domains:
            alias.append("www.%s" % domain)
        upload_template("../templates/simple_vhost", "/etc/apache2/sites-available/%s" % main_domain, {
            "NAME": name,
            "DOMAIN": main_domain,
            "ALIAS": " ".join(alias)
        }, use_sudo=True)
        if not cuisine.file_exists("/etc/apache2/sites-enabled/%s" % main_domain):
            cuisine.file_link("/etc/apache2/sites-available/%s" % main_domain, "/etc/apache2/sites-enabled/%s" % main_domain)
    restart_apache()

def restart_apache():
    sudo("/etc/init.d/apache2 restart")

