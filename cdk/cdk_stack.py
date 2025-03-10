from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_s3 as s3,
    aws_s3_notifications as s3_notifications,
    aws_lambda as _lambda, Duration,
)
from constructs import Construct


class DashboardStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Create a VPC without NAT Gateways
        vpc = ec2.Vpc(
            self,
            "DashboardVPC",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # Add VPC Endpoints for necessary AWS services
        vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
        )

        # Interface endpoints for ECS, ECR, and CloudWatch
        vpc.add_interface_endpoint(
            "EcsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECS,
        )
        vpc.add_interface_endpoint(
            "EcsAgentEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECS_AGENT,
        )
        vpc.add_interface_endpoint(
            "EcsTelemetryEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECS_TELEMETRY,
        )
        vpc.add_interface_endpoint(
            "EcrEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR,
        )
        vpc.add_interface_endpoint(
            "EcrDockerEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
        )
        vpc.add_interface_endpoint(
            "LogsEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
        )

        # Create an ECS Cluster inside the VPC
        cluster = ecs.Cluster(self, "DashboardCluster", vpc=vpc)

        # Create a new ECR Repository to store Docker images
        repository = ecr.Repository.from_repository_name(
            self, "VVDashboardRepo", "v-v_dashboard"
        )

        # Create the S3 bucket with cleanup policies
        # s3_bucket = s3.Bucket(
        #     self,
        #     "BenchmarkDataBucket",
        #     bucket_name="benchmark-vv-data",
        #     versioned=True,
        #     removal_policy=RemovalPolicy.RETAIN,
        # )
        # Reference the existing S3 bucket
        s3_bucket = s3.Bucket.from_bucket_name(
            self,
            "BenchmarkDataBucket",
            bucket_name="benchmark-vv-data"
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
        s3_bucket.grant_read(task_role, "public_ds/*")
        s3_bucket.grant_read(task_role, "benchmark_templates/*")

        # Define the ECS Task Definition using the Docker image from ECR
        task_definition = ecs.FargateTaskDefinition(
            self,
            "DashboardTaskDef",
            memory_limit_mib=8192,
            cpu=1024,
            execution_role=task_role,
            task_role=task_role,
        )

        # Add a container to the task definition
        container = task_definition.add_container(
            "DashboardContainer",
            image=ecs.ContainerImage.from_ecr_repository(repository, "2.1.2"),
            logging=ecs.LogDrivers.aws_logs(stream_prefix="DashboardApp"),
        )
        container.add_port_mappings(ecs.PortMapping(container_port=8050))

        # Define a Fargate Service with an Application Load Balancer
        fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "DashboardFargateService",
            cluster=cluster,
            task_definition=task_definition,
            public_load_balancer=True,
        )

        lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )

        # Policy for reading objects from `upload/` prefix:
        # Allows listing the bucket (with a condition restricting it to the `upload/` prefix)
        # and getting objects only from that prefix.
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:ListBucket"],
                resources=["arn:aws:s3:::my-bucket"],
                conditions={
                    "StringLike": {
                        "s3:prefix": "upload/"
                    }
                }
            )
        )

        # Grant read access (GetObject) on objects under upload/ and benchmark_templates/
        s3_bucket.grant_read(lambda_role, "upload/*")
        s3_bucket.grant_read(lambda_role, "benchmark_templates/*")


        # Grant write access (PutObject) on objects under public_ds/
        s3_bucket.grant_put(lambda_role, "public_ds/*")

        repo = ecr.Repository.from_repository_name(
            self,
            "VvLambdaUploadRepo",
            repository_name="vv-lambda-upload",
        )

        # Lambda function to use the manually pushed Docker image
        process_uploads = _lambda.DockerImageFunction(
            self,
            "ProcessUploadsLambda",
            function_name="process_uploads",
            code=_lambda.DockerImageCode.from_ecr(
                repository=repo,
                tag="2.0.6",
            ),
            timeout=Duration.minutes(5),
            memory_size=8192,
            role=lambda_role,
        )

        # Add notification to trigger Lambda when a folder is uploaded
        s3_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3_notifications.LambdaDestination(process_uploads),
            s3.NotificationKeyFilter(prefix="upload/")
        )
