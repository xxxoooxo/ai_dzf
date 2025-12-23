@echo off
set LOG_FILE=server_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%.log
set LOG_FILE=%LOG_FILE: =0%
echo Starting server with logging to %LOG_FILE%
python start_server.py 2>&1 | python -u -c "import sys; [print(line, end='', flush=True) or open('%LOG_FILE%', 'a', encoding='utf-8').write(line) for line in sys.stdin]"

