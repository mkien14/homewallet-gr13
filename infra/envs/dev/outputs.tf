output "vpc_id" { value = module.network.vpc_id }
output "public_subnet_ids" { value = module.network.public_subnet_ids }
output "app_subnet_ids" { value = module.network.app_subnet_ids }
output "data_subnet_ids" { value = module.network.data_subnet_ids }
output "sg_ids" { value = module.network.sg_ids }
output "ecr_url" { value = module.ecr.repository_url }
output "alb_dns_name" { value = module.compute.alb_dns_name }