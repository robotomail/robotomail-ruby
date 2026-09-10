# frozen_string_literal: true
require "net/http"
require "json"
require "openssl"
require "uri"
require "securerandom"

module Robotomail
  Upload = Struct.new(:data, :filename, :content_type, keyword_init: true)
  EventFrame = Struct.new(:data, :event, :id, keyword_init: true)

  class ApiError < StandardError
    attr_reader :status, :body, :headers, :code
    def initialize(status, body, headers)
      @status, @body, @headers = status, body, headers
      @code = body["code"] if body.is_a?(Hash)
      super(body.is_a?(Hash) && body["error"] || "Robotomail HTTP #{status}")
    end
  end

  def self.verify_webhook(payload, signature, secret)
    return false if secret.empty? || !signature.match?(/\A[0-9a-f]{64}\z/)
    expected = OpenSSL::HMAC.hexdigest("SHA256", secret, payload)
    OpenSSL.fixed_length_secure_compare(expected, signature)
  end

  class Transport
    def initialize(api_key: ENV["ROBOTOMAIL_API_KEY"], base_url: "https://api.robotomail.com/v1", timeout: 30)
      uri = URI(base_url)
      unless !uri.userinfo && !uri.query && !uri.fragment && uri.host &&
             (uri.scheme == "https" || uri.scheme == "http" && ["localhost", "127.0.0.1", "[::1]"].include?(uri.host))
        raise ArgumentError, "base_url must be HTTPS, or HTTP on localhost, without credentials, query or fragment"
      end
      raise ArgumentError, "timeout must be positive" unless timeout.positive?
      @api_key, @base_url, @timeout = api_key, base_url.sub(%r{/$}, ""), timeout
    end

    private

    def segment(value)
      raise ArgumentError, "Resource IDs must be nonempty path segments" if value.to_s.empty? || [".", ".."].include?(value)
      URI.encode_www_form_component(value).gsub("+", "%20")
    end

    def prepare(path, params, streaming: false)
      uri = URI(@base_url + path)
      headers = {"Accept" => streaming ? "text/event-stream" : "application/json", "User-Agent" => "robotomail-ruby/0.1.0"}
      headers["Authorization"] = "Bearer #{@api_key}" if @api_key && !@api_key.empty?
      query = {}
      params.each do |key, value|
        next if value.nil?
        key.to_s == "Last-Event-ID" ? headers[key.to_s] = value.to_s : query[key] = value
      end
      uri.query = URI.encode_www_form(query) unless query.empty?
      [uri, headers]
    end

    def connection(uri, streaming: false)
      http = Net::HTTP.new(uri.hostname, uri.port)
      http.use_ssl = uri.scheme == "https"
      http.open_timeout = @timeout
      http.read_timeout = streaming ? [@timeout, 60].max : @timeout
      http.write_timeout = @timeout
      http.max_retries = 0
      http
    end

    def decode(response, raw)
      status = response.code.to_i
      begin
        body = raw.empty? ? nil : JSON.parse(raw)
      rescue JSON::ParserError
        raise "Robotomail returned invalid JSON" if (200...300).cover?(status)
        body = raw
      end
      raise ApiError.new(status, body, response.each_header.to_h) unless (200...300).cover?(status)
      body
    end

    def request(method, path, body: nil, params: {}, file: nil)
      uri, headers = prepare(path, params)
      payload = nil
      if file
        raise ArgumentError, "Invalid filename" if file.filename.match?(/[\r\n]/)
        raise ArgumentError, "Attachments must be at most 25 MB" if file.data.bytesize > 25 * 1024 * 1024
        boundary = "robotomail-#{SecureRandom.hex(16)}"
        filename = file.filename.gsub('\\', '\\\\').gsub('"', '\\"')
        content_type = file.content_type || "application/octet-stream"
        raise ArgumentError, "Invalid content type" if content_type.match?(/[\r\n]/)
        headers["Content-Type"] = "multipart/form-data; boundary=#{boundary}"
        payload = "--#{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"#{filename}\"\r\nContent-Type: #{content_type}\r\n\r\n".b + file.data.b + "\r\n--#{boundary}--\r\n".b
      elsif !body.nil?
        headers["Content-Type"] = "application/json"
        payload = JSON.generate(body)
      end
      req = Net::HTTPGenericRequest.new(method, !payload.nil?, true, uri.request_uri, headers)
      req.body = payload if payload
      connection(uri).start do |http|
        response = http.request(req)
        decode(response, response.body || "")
      end
    end

    def stream(params)
      Enumerator.new do |yielded|
        uri, headers = prepare("/events", params, streaming: true)
        connection(uri, streaming: true).start do |http|
          http.request(Net::HTTP::Get.new(uri.request_uri, headers)) do |response|
            unless (200...300).cover?(response.code.to_i)
              raw = +""
              response.read_body { |chunk| raw << chunk }
              decode(response, raw)
            end
            raise "Robotomail returned a non-SSE response" unless response["content-type"].to_s.start_with?("text/event-stream")
            buffer, data, event, id, size = +"".b, [], "message", nil, 0
            response.read_body do |chunk|
              buffer << chunk.b
              raise "SSE event exceeds 1 MB" if buffer.bytesize + size > 1024 * 1024
              while (match = buffer.match(/\r\n|\r|\n/))
                break if match[0] == "\r" && match.begin(0) == buffer.bytesize - 1
                line = buffer.slice!(0, match.end(0)).byteslice(0, match.begin(0)).force_encoding("UTF-8")
                if line.empty?
                  yielded << EventFrame.new(data: data.join("\n"), event: event, id: id) unless data.empty?
                  data, event, size = [], "message", 0
                  next
                end
                size += line.bytesize
                key, value = line.split(":", 2)
                value = (value || "").sub(/^ /, "")
                case key
                when "data" then data << value
                when "event" then event = value
                when "id" then id = value unless value.include?("\0")
                end
              end
            end
          end
        end
      end
    end
  end
end
