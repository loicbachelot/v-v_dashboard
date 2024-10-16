#!/usr/bin/env python3
import aws_cdk as cdk
from cdk_stack import DashboardStack

app = cdk.App()
DashboardStack(app, "DashboardStack")
app.synth()