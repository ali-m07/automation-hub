.PHONY: help build run test docker-build docker-run docker-compose-up docker-compose-down k8s-deploy k8s-delete k8s-status clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Local Development
build: ## Install dependencies
	pip install -r requirements.txt

run: ## Run application locally
	python app.py

run-script: ## Run using startup script (Unix)
	bash scripts/start.sh

run-script-win: ## Run using startup script (Windows)
	scripts\start.bat

test: ## Run all tests
	pytest tests/ -v

test-unit: ## Run unit tests only
	pytest tests/unit/ -v -m unit

test-integration: ## Run integration tests only
	pytest tests/integration/ -v -m integration

test-cov: ## Run tests with coverage report
	pytest tests/ --cov=automation_hub --cov-report=html --cov-report=term-missing

test-fast: ## Run tests without coverage (faster)
	pytest tests/ -v --no-cov

# Docker Commands
docker-build: ## Build Docker image
	docker build -f docker/Dockerfile -t automation-hub:latest .

docker-run: ## Run Docker container
	docker run -d -p 8000:8000 \
		-v $(PWD)/uploads:/app/uploads \
		-v $(PWD)/outputs:/app/outputs \
		--name automation-hub \
		automation-hub:latest

docker-stop: ## Stop Docker container
	docker stop automation-hub || true
	docker rm automation-hub || true

docker-logs: ## View Docker logs
	docker logs -f automation-hub

# Docker Compose
docker-compose-up: ## Start services with docker-compose
	cd docker && docker-compose -f docker-compose.yml up -d

docker-compose-down: ## Stop docker-compose services
	cd docker && docker-compose -f docker-compose.yml down

docker-compose-logs: ## View docker-compose logs
	cd docker && docker-compose -f docker-compose.yml logs -f

docker-compose-up-nginx: ## Start with Nginx reverse proxy
	cd docker && docker-compose -f docker-compose.yml -f docker-compose.nginx.yml up -d

docker-compose-up-redis: ## Start with Redis
	cd docker && docker-compose -f docker-compose.yml -f docker-compose.redis.yml up -d

# Kubernetes Commands
k8s-namespace: ## Create Kubernetes namespace
	kubectl create namespace psd-converter || true

k8s-deploy: k8s-namespace ## Deploy to Kubernetes
	cd k8s && kubectl apply -k . -n psd-converter

k8s-delete: ## Delete Kubernetes deployment
	cd k8s && kubectl delete -k . -n psd-converter

k8s-status: ## Check Kubernetes status
	kubectl get all -n psd-converter

k8s-logs: ## View Kubernetes logs
	kubectl logs -f deployment/psd-converter -n psd-converter

k8s-port-forward: ## Port forward to local machine
	kubectl port-forward svc/psd-converter-service 8000:80 -n psd-converter

k8s-update-image: ## Update image tag (usage: make k8s-update-image TAG=v1.0.0)
	cd k8s && kustomize edit set image psd-converter:$(TAG)
	kubectl apply -k . -n psd-converter

# CI/CD
ci-test: ## Run CI tests
	pip install -r requirements.txt
	pytest --cov=. --cov-report=xml || true

# Cleanup
clean: ## Clean temporary files
	find . -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov dist build

clean-docker: ## Clean Docker images and containers
	docker stop automation-hub 2>/dev/null || true
	docker rm automation-hub 2>/dev/null || true
	docker rmi automation-hub:latest 2>/dev/null || true
	cd docker && docker-compose -f docker-compose.yml down -v 2>/dev/null || true

clean-all: clean clean-docker ## Clean everything
