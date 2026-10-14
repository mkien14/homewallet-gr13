output "vpc_id"            { value = aws_vpc.this.id }
output "public_subnet_ids" { value = aws_subnet.public[*].id }
output "app_subnet_ids"    { value = aws_subnet.app[*].id }
output "data_subnet_ids"   { value = aws_subnet.data[*].id }

output "sg_ids" {
  value = {
    alb       = aws_security_group.alb.id
    app       = aws_security_group.app.id
    db        = aws_security_group.db.id
    cache     = aws_security_group.cache.id
    endpoints = aws_security_group.endpoints.id
  }
}