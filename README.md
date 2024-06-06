# AWS Lambda Function to create or Update Route53 entries with private ips

## Summary

This Lambda function allows you to use an AWS ELB (application loadbalancer) that is configured as a public loadbalancer to also balance private loads by keeping the private IPS up to date in a Route53 record.
Run this lambda function every x minutes to check if the IPs of the loadbalancers changed (by checking network interfaces). It updates the event parameters to save the last status and when IPs changed, it will update the specified Route53 record.

## Deploy

To use this plugin:

* Clone this repo
* Set the following parameters at the top of lambda_function.py
    * `EVENT_NAME` -> CloudWatch-Event name the function listens to<br>**(Must Not have any other targets than this lambda function)**
    * `HOSTED_ZONE_ID` -> The route53 hosted zone where entries get updated
    * `DNS_MAPPING` -> Mapping of public hostnames to private hostnames for domains which should be created / updated
* run `zip -r -X '../updateprivateELBrecord.zip' lambda_function.py` from the repository root to create a zipfile with all content to upload to Lambda
* Create a function on AWS for Lambda and update the zip file
* Create a cloudwatch event that runs the lambda at the desired interval (make sure the name of the event matches the parameter in index.js)

**Notice**: The first time it will run slow and take about 5 seconds to complete.

## IAM Setting

Besides the normal Lambda policy to write to CloudWatch logs, you also need the following policy:
(Replace _ACCOUNTID_ with your accountid, _ZONEID_ with the route53 zone and _FUNCTIONNAME_ with the name of the lambda function)

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": "ec2:DescribeNetworkInterfaces",
            "Resource": "*"
        },
        {
            "Sid": "VisualEditor1",
            "Effect": "Allow",
            "Action": [
                "events:PutTargets",
                "route53:ChangeResourceRecordSets",
                "events:ListTargetsByRule"
            ],
            "Resource": [
                "arn:aws:events:*:_ACCOUNTID_:rule/_FUNCTIONNAME_",
                "arn:aws:route53:::hostedzone/_ZONEID_"
            ]
        }
    ]
}
```