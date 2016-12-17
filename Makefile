kill:
	ps -A | grep "python run_bot.py" | grep -v grep | awk '{print $$1}' | xargs kill -9
run:
	python run_bot.py
restart:
	make kill; make run
serve:
	python run_bot.py &
	fswatch -0 . --exclude=".git" | xargs -0 -n1 -I{} make restart
