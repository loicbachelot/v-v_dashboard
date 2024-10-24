from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_s3 as s3,
)
from constructs import Construct

class DashboardStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Create a VPC for ECS Fargate
        vpc = ec2.Vpc(self, "DashboardVPC", max_azs=2)

        # Add an S3 VPC Endpoint to the VPC
        s3_endpoint = vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3
        )

        # Create an ECS Cluster inside the VPC
        cluster = ecs.Cluster(self, "DashboardCluster", vpc=vpc)

        # Create a new ECR Repository to store Docker images
        repository = ecr.Repository.from_repository_name(
            self, "VVDashboardRepo", "v-v_dashboard"
        )

        # Create the S3 bucket with cleanup policies
        s3_bucket = s3.Bucket(
            self,
            "BenchmarkDataBucket",
            bucket_name="benchmark-vv-data",
            versioned=True,  # Optional: Enable versioning
            removal_policy=RemovalPolicy.DESTROY,  # Cleanup on stack deletion
            auto_delete_objects=True,  # Automatically delete objects with the bucket
        )

        # Grant permissions for the ECS task to read from the S3 bucket
        task_role = iam.Role(
            self,
            "DashboardTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                ),
            ],
        )
        s3_bucket.grant_read(task_role)

        # Define the ECS Task Definition using the Docker image from ECR
        task_definition = ecs.FargateTaskDefinition(
            self,
            "DashboardTaskDef",
            memory_limit_mib=8192,
            cpu=1024,
            execution_role=task_role,
            task_role=task_role,  # Use the same role to access resources
        )

        # Add a container to the task definition
        container = task_definition.add_container(
            "DashboardContainer",
            image=ecs.ContainerImage.from_ecr_repository(repository),
            logging=ecs.LogDrivers.aws_logs(stream_prefix="DashboardApp"),
        )
        container.add_port_mappings(ecs.PortMapping(container_port=8050))

        # Define a Fargate Service with an Application Load Balancer
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "DashboardFargateService",
            cluster=cluster,
            task_definition=task_definition,
            public_load_balancer=True,  # Make the service accessible publicly
        )
