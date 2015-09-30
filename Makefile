run:
	docker-machine start default
	eval "$(docker-machine env default)"
	docker-compose up

build:
	docker-machine start default
	eval "$(docker-machine env default)"
	docker-compose build

.PHONY: run build
