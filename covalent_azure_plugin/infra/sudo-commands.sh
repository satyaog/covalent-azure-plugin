_data_fs=$(df --output=avail,target --exclude-type=tmpfs | sort | tail -n1 | cut -d" " -f2)
mkdir ${_data_fs}/data
chmod a+rwX ${_data_fs}/data
[ ! -d /data ] && ln -sf ${_data_fs}/data /data

! apt update
# Install htop only to wait for lock file to be released. Then nvidia-smi will
# become available
while ! timeout 60s apt install -y htop
do
    >&2 echo "Waiting for apt lock file to be released"
    sleep 1
done

echo 'PATH="/home/ubuntu/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games:/snap/bin"' > /etc/environment
