# SSM-only bastion for ad-hoc RDS access (psql, one-off debugging queries) — NOT part of the
# automated migration path (see modules/lambda_migrate for that). No SSH: access is entirely
# via `aws ssm start-session`, so there's no key to manage and no port 22 ever open. Sits in
# the public subnet with a public IP so it can reach the SSM service over the internet without
# needing a NAT gateway or VPC interface endpoints (would cost more than this whole instance).
# Security group has zero ingress rules — nothing can initiate a connection to it from outside;
# SSM works entirely over outbound HTTPS.
#
# Stop it when not in use to cut cost to ~storage only: `aws ec2 stop-instances --instance-ids <id>`.

data "aws_ami" "al2023_arm64" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-*-arm64"]
  }
}

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${var.name}-bastion"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "this" {
  name = "${var.name}-bastion"
  role = aws_iam_role.this.name
}

resource "aws_security_group" "this" {
  name_prefix = "${var.name}-bastion-"
  vpc_id      = var.vpc_id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  # No ingress rules at all — SSM Session Manager needs none.
}

resource "aws_vpc_security_group_ingress_rule" "db_from_bastion" {
  security_group_id            = var.db_security_group_id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.this.id
  description                  = "bastion -> RDS, for SSM port-forward (psql, ad-hoc queries)"
}

resource "aws_instance" "this" {
  ami                         = data.aws_ami.al2023_arm64.id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.this.id]
  iam_instance_profile        = aws_iam_instance_profile.this.name
  associate_public_ip_address = true

  root_block_device {
    volume_size = 8
    volume_type = "gp3"
  }

  tags = { Name = "${var.name}-bastion" }
}
