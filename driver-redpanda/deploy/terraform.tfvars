public_key_path = "~/.ssh/redpanda_aws.pub"
region          = "eu-west-1"
az		        = "eu-west-1a"
ami             = "ami-022e8cc8f0d3c52fd"
profile         = "default"

instance_types = {
  "redpanda"      = "i3en.6xlarge"
  "client"        = "m5.large"
  "prometheus"    = "c5.2xlarge"
}

num_instances = {
  "client"     = 2
  "redpanda"   = 0
  "prometheus" = 0
}
