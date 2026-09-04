<?php
/**
 * Hostinger In-Process Python CGI Gateway for Guasha House
 * Runs FastAPI directly per-request without relying on fragile background daemons
 */

// Disable buffering for instant streaming
while (ob_get_level()) {
    ob_end_clean();
}

$dir = __DIR__;
$python = file_exists("$dir/venv/bin/python") ? "$dir/venv/bin/python" : (file_exists("/home/u713703050/python/bin/python3") ? "/home/u713703050/python/bin/python3" : "python3");

// Prepare CGI Environment
$env = $_SERVER;

// Normalize CGI environment variables for WSGI
$uri = $_SERVER['REQUEST_URI'] ?? '/';
$parsed = parse_url($uri);
$env['PATH_INFO'] = $parsed['path'] ?? '/';
$env['SCRIPT_NAME'] = '';
$env['QUERY_STRING'] = $parsed['query'] ?? '';
$env['REQUEST_METHOD'] = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$env['SERVER_NAME'] = $_SERVER['SERVER_NAME'] ?? ($_SERVER['HTTP_HOST'] ?? 'guashahouse.com');
$env['SERVER_PORT'] = $_SERVER['SERVER_PORT'] ?? '443';
$env['SERVER_PROTOCOL'] = $_SERVER['SERVER_PROTOCOL'] ?? 'HTTP/1.1';
$env['wsgi.url_scheme'] = (isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on') ? 'https' : 'http';

// Forward HTTP Headers
$headers = function_exists('getallheaders') ? getallheaders() : [];
foreach ($headers as $k => $v) {
    $env_name = 'HTTP_' . strtoupper(str_replace('-', '_', $k));
    $env[$env_name] = $v;
}
if (!empty($_SERVER['HTTP_COOKIE'])) {
    $env['HTTP_COOKIE'] = $_SERVER['HTTP_COOKIE'];
}
if (!empty($_SERVER['CONTENT_TYPE'])) {
    $env['CONTENT_TYPE'] = $_SERVER['CONTENT_TYPE'];
}
if (!empty($_SERVER['CONTENT_LENGTH'])) {
    $env['CONTENT_LENGTH'] = $_SERVER['CONTENT_LENGTH'];
}

$descriptorspec = [
    0 => ["pipe", "r"], // stdin
    1 => ["pipe", "w"], // stdout
    2 => ["pipe", "w"]  // stderr
];

$cmd = escapeshellcmd($python) . " " . escapeshellarg("$dir/wsgi_runner.py");
$process = proc_open($cmd, $descriptorspec, $pipes, $dir, $env);

if (!is_resource($process)) {
    http_response_code(500);
    echo "<h1>Error: Unable to launch Python runtime</h1>";
    exit;
}

// Write request body to stdin if POST/PUT/PATCH
if (in_array($env['REQUEST_METHOD'], ['POST', 'PUT', 'PATCH', 'DELETE'])) {
    $input = file_get_contents('php://input');
    if ($input) {
        fwrite($pipes[0], $input);
    }
}
fclose($pipes[0]);

// Read headers and body from Python output
$response_headers_raw = '';
$headers_done = false;

while (!feof($pipes[1])) {
    $line = fgets($pipes[1]);
    if ($line === false) break;

    if (!$headers_done) {
        if (trim($line) === '') {
            $headers_done = true;
            continue;
        }
        
        // Process Header
        $trimmed = trim($line);
        if (stripos($trimmed, 'Status:') === 0) {
            $status_parts = explode(' ', substr($trimmed, 7), 2);
            http_response_code((int)trim($status_parts[0]));
        } else {
            header($trimmed, false);
        }
    } else {
        echo $line;
    }
}

fclose($pipes[1]);
$stderr = stream_get_contents($pipes[2]);
fclose($pipes[2]);
proc_close($process);

if (!$headers_done && !empty($stderr)) {
    http_response_code(500);
    echo "<pre>Backend Error:\n" . htmlspecialchars($stderr) . "</pre>";
}
