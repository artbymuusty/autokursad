import os
import stat

scripts = [
    '/home/muusty/autokursad/.scripts/olds/v34/run_mission_v34_gz.sh',
    '/home/muusty/autokursad/.scripts/olds/v34/run_mission_v34_real.sh',
    '/home/muusty/autokursad/.scripts/olds/v34/run_mission_v34_dual.sh'
]

for s in scripts:
    st = os.stat(s)
    os.chmod(s, st.st_mode | stat.S_IEXEC)
