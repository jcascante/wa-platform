# Single-AZ db.t4g.micro to start (~$12-13/mo) — cheapest managed Postgres that still gets
# automated backups and patching. Move to Multi-AZ / a larger class / RDS Proxy once real
# traffic lands; RDS Proxy in particular becomes worth its cost once Lambda concurrency is
# high enough to risk exhausting Postgres connections.

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-db"
  subnet_ids = var.private_subnet_ids
}

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_db_instance" "this" {
  identifier              = "${var.name}-db"
  engine                  = "postgres"
  engine_version          = "16"
  instance_class          = var.instance_class
  allocated_storage       = 20
  storage_type            = "gp3"
  db_name                 = "platform"
  username                = "platform"
  password                = random_password.db.result
  db_subnet_group_name    = aws_db_subnet_group.this.name
  vpc_security_group_ids  = [var.db_security_group_id]
  multi_az                = false
  publicly_accessible     = false
  skip_final_snapshot     = var.environment != "prod"
  deletion_protection     = var.environment == "prod"
  backup_retention_period = 7
}

resource "aws_secretsmanager_secret" "db_url" {
  name = "${var.name}-database-url"
}

resource "aws_secretsmanager_secret_version" "db_url" {
  secret_id     = aws_secretsmanager_secret.db_url.id
  secret_string = "postgresql+psycopg://${aws_db_instance.this.username}:${random_password.db.result}@${aws_db_instance.this.endpoint}/${aws_db_instance.this.db_name}"
}
