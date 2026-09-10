require_relative "lib/robotomail"
Gem::Specification.new do |spec|
  spec.name = "robotomail"
  spec.version = Robotomail::VERSION
  spec.authors = ["Robotomail"]
  spec.email = ["support@robotomail.com"]
  spec.summary = "Official Robotomail SDK for Ruby"
  spec.description = "Send and receive agent email, manage mailboxes and webhooks, and stream inbox events."
  spec.homepage = "https://robotomail.com"
  spec.license = "MIT"
  spec.required_ruby_version = ">= 3.1"
  spec.files = Dir["lib/**/*.rb"] + ["README.md", "API.md", "LICENSE"]
  spec.require_paths = ["lib"]
  spec.metadata = {"source_code_uri" => "https://github.com/robotomail/robotomail-ruby", "documentation_uri" => "https://robotomail.com/docs", "rubygems_mfa_required" => "true"}
  spec.add_dependency "net-http", ">= 0.4", "< 1"
  spec.add_dependency "openssl", ">= 3", "< 5"
end
