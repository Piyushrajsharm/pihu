resource "aws_ecs_cluster" "pihu_cluster" {
  name = "${var.project_name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_ecs_task_definition" "pihu_task" {
  family                   = "${var.project_name}-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "2048"

  container_definitions = jsonencode([
    {
      name  = "pihu-backend"
      image = var.container_image
      cpu   = 512
      memory = 1024
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
        }
      ]
      environment = [
        { name = "DATABASE_URL", value = "TBD_FROM_RDS" },
        { name = "REDIS_URL", value = "TBD_FROM_ELASTICACHE" }
      ]
    }
  ])
}

resource "aws_ecs_service" "pihu_service" {
  name            = "${var.project_name}-service"
  cluster         = aws_ecs_cluster.pihu_cluster.id
  task_definition = aws_ecs_task_definition.pihu_task.arn
  desired_count   = 2
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = [aws_subnet.public_subnet.id]
    security_groups = [aws_security_group.ecs_tasks_sg.id]
    assign_public_ip = true
  }
}
