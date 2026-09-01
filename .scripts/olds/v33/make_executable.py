import os
import stat

scripts = [
    '/home/muusty/autokursad/.scripts/olds/v33/run_mission_v33_gz.sh',
    '/home/muusty/autokursad/.scripts/olds/v33/run_mission_v33_real.sh',
    '/home/muusty/autokursad/.scripts/olds/v33/run_mission_v33_dual.sh'
]

for s in scripts:
    st = os.stat(s)
    os.chmod(s, st.st_mode | stat.S_IEXEC)
