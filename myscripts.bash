#!/bin/sh
# source these from bashrc in order to devine functions.

# we might want to use host networking so that dds can use multicast
# multicast over a docker bridge is notoriously bad/.
unset -f ranger3_cpuc_sync
unset -f strider1_sync
unset -f strider2_sync
unset -f strider1_test
unset -f strider2_test
docker_run_gazebo(){
    set -e
    xhost +
    docker run --net=host -it --rm -e DISPLAY=$DISPLAY -v /tmp/.X11-unix:/tmp/.X11-unix:ro --shm-size=512M gazebo $@
}
ranger3_cpuc_sync(){
    pushd ~/src/ranger/meta-sws/NgmpDomestic/x86_64/linux/g++4.8.x/Release
    rsync --progress -crlpDv -e "ssh -l cpuc" . ranger3_cpuc:/home/cpuc/jv_sws/
    #rsync -vaz --progress --exclude Standard_Demo_Waveform_Set.dat * ranger3_cpuc:~/jv_sws
    popd
}
ranger3_sync(){
    pushd ~/src/ranger/meta-sws/meta-vst/NgmpICMBuildArmRelease/Output/armdef/linux/g++4.8.2
    SSHPASS="master(&"
    #sshpass -p $SSHPASS scp NgmpCobhamApiServant ranger3_vst:/usr/bin
    sshpass -p $SSHPASS rsync -l --checksum --existing -vr --exclude "*Test*" . ranger3_vst:/usr/bin
    sshpass -p $SSHPASS rsync -l --checksum --existing -vr --exclude "*Test*" . ranger3_vst:/usr/lib
    popd
}
ranger3_test(){
    time ssh ranger3_cpuc source vishnefske/notes.txt
}
setNgmp(){
  export  NGMP_DIR=/opt/Ngmp
  export LD_LIBRARY_PATH=/opt/Ngmp/lib
}
strider2_sync(){
    workspace=$HOME/src/meta-strider
    host=strider2_slice
    bindir=$workspace/cmake_build/slice/Output/armdef/linux/g++4.8.2
    # the password is stored in a file
    # command for vst interactive engine
    # /opt/Ngmp/bin/VstInteractive --simulatedApi false --loglevel Info
    masterpass ssh $host 'echo  export NGMP_DIR=/opt/Ngmp LD_LIBRARY_PATH=/tmp:/opt/Ngmp/lib > /tmp/setenv.sh'
    masterpass rsync -av ${bindir}/*PowerDropOut* ${bindir}/lib*  $host:/tmp
    ${HOME}/src/DSP_Prebuilt/lib_arm/libAlgorithmsSDR*:/tmp
}
strider2_test(){
    masterpass ssh strider2_slice 'source /tmp/setenv.sh; /tmp/PowerDropOutClientUnitTest '
}
strider2_powerdropoutengine(){
    masterpass ssh strider2_slice 'source /tmp/setenv.sh; /tmp/PowerDropOutEngine'
}
docker_run_cx700_workspace(){
    #docker volume create --driver local --opt type=bind --opt device=~/src/ src 
    #docker run --name strider-build -v src:/space/src -it cx700 /bin/bash
    docker run --mount type=bind,src=/space,destination=/space -it cx700 /bin/bash
}
uptime
