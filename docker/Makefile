# Commands
# I = Image-name
# C = Container-name

permit:
	sudo chmod -R 777 /var/run/docker.sock
	
build:
	docker build -t $(I) .

run:
	docker run -v /home/ubuntu/consumer_affairs_dashboard:/main -v /etc/localtime:/etc/localtime:ro --net="host" --gpus all -it -d $(C):latest

i:
	docker images

ps:
	docker ps
	
name:
	docker ps --filter "ancestor=$(C)" --format "{{.Names}}" 
	
s:
	docker exec -it $(I) bash
	
start:
	docker exec -it $(I) bash -c 'cd /main/api && uvicorn main:app --host 127.0.0.1 --port 3042 --workers 7 --reload'

docstart:
	cd /main/api && uvicorn main:app --host 127.0.0.1 --port 3042 --workers 7 --reload

stop:
	docker stop $(C)

cleani:
	docker rmi $(I)

cleanc:
	docker rm -f $(C)