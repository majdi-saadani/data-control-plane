output "ecr_repository_url" {
  description = "Push the API image here (tag: latest)"
  value       = module.api_registry.repository_url
}

output "ecs_cluster_name" {
  value = module.api.cluster_name
}

output "ecs_service_name" {
  value = module.api.service_name
}

output "github_deploy_role_arn" {
  description = "Set this as the AWS_DEPLOY_ROLE_ARN repository variable in GitHub"
  value       = module.github_deploy.role_arn
}

output "event_generator_function_name" {
  value = module.event_generator.function_name
}

output "tracking_table_name" {
  value = module.pipeline_runs_table.table_name
}

output "api_public_ip_command" {
  description = "No load balancer: find the task's public IP with this command, then open http://<ip>:8000/docs"
  value       = <<-EOT
    TASK=$(aws ecs list-tasks --cluster ${module.api.cluster_name} --service-name ${module.api.service_name} --query 'taskArns[0]' --output text)
    ENI=$(aws ecs describe-tasks --cluster ${module.api.cluster_name} --tasks $TASK --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text)
    aws ec2 describe-network-interfaces --network-interface-ids $ENI --query 'NetworkInterfaces[0].Association.PublicIp' --output text
  EOT
}
