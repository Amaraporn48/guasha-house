<?php
/**
 * Guasha House High-Performance LiteSpeed Proxy & Auto-Healer
 */

ini_set('display_errors', 0);
error_reporting(0);

$backend_host = "http://127.0.0.1:8000";
$dir = __DIR__;

function start_uvicorn_backend($force = false) {
    global $dir;
    if ($force) {
        @exec("pkill -f 'uvicorn main:app' 2>/dev/null");
        @exec("pkill -f 'hostinger_run.sh' 2>/dev/null");
        usleep(300000);
    }
    
    $pythons = [
        "$dir/venv/bin/python",
        "$dir/venv/bin/python3",
        "/home/u713703050/python/bin/python3",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
        "python3"
    ];
    $python = "python3";
    foreach ($pythons as $p) {
        if (file_exists($p) && is_executable($p)) {
            $python = $p;
            break;
        }
    }
    
    if (file_exists("$dir/hostinger_run.sh")) {
        $cmd = "cd $dir && bash hostinger_run.sh > hostinger_start.log 2>&1 &";
    } else {
        $cmd = "cd $dir && nohup $python -m uvicorn main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips '*' > uvicorn.log 2>&1 &";
    }
    @exec($cmd);
    
    for ($i = 0; $i < 25; $i++) {
        usleep(200000);
        $fp = @fsockopen('127.0.0.1', 8000, $errno, $errstr, 0.2);
        if ($fp) {
            fclose($fp);
            return true;
        }
    }
    return false;
}

// Manual force restart handler
if (isset($_GET['restart'])) {
    start_uvicorn_backend(true);
    header("Location: /");
    exit;
}

// Check backend availability
$fp = @fsockopen('127.0.0.1', 8000, $errno, $errstr, 0.1);
if (!$fp) {
    start_uvicorn_backend();
} else {
    fclose($fp);
}

$request_uri = $_SERVER['REQUEST_URI'] ?? '/';
$target_url = $backend_host . $request_uri;

$ch = curl_init($target_url);

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_HEADER, true);
curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
curl_setopt($ch, CURLOPT_TIMEOUT, 20);
curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 4);
curl_setopt($ch, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_1_1);

// Forward all incoming request headers
$headers = [];
$incoming_headers = function_exists('getallheaders') ? getallheaders() : [];

$has_cookie = false;
foreach ($incoming_headers as $name => $value) {
    $lower = strtolower($name);
    if (!in_array($lower, ['host', 'content-length', 'connection'])) {
        $headers[] = "$name: $value";
    }
    if ($lower === 'cookie') {
        $has_cookie = true;
    }
}

if (!$has_cookie && !empty($_SERVER['HTTP_COOKIE'])) {
    $headers[] = "Cookie: " . $_SERVER['HTTP_COOKIE'];
}

$headers[] = "Host: " . ($_SERVER['HTTP_HOST'] ?? 'guashahouse.com');
$headers[] = "X-Real-IP: " . ($_SERVER['REMOTE_ADDR'] ?? '127.0.0.1');
$headers[] = "X-Forwarded-For: " . ($_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'] ?? '127.0.0.1');
$headers[] = "X-Forwarded-Proto: " . ((isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on') ? 'https' : 'http');

// Forward body
if (in_array($method, ['POST', 'PUT', 'PATCH', 'DELETE'])) {
    $body = file_get_contents('php://input');
    curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
    if (!empty($_SERVER['CONTENT_TYPE'])) {
        $headers[] = "Content-Type: " . $_SERVER['CONTENT_TYPE'];
    }
}

curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

$response = curl_exec($ch);

if ($response === false) {
    curl_close($ch);
    http_response_code(503);
    header('Content-Type: text/html; charset=utf-8');
    
    $log_content = "";
    if (file_exists("$dir/uvicorn.log")) {
        $log_content .= htmlspecialchars(substr(file_get_contents("$dir/uvicorn.log"), -1500));
    }
    if (file_exists("$dir/hostinger_start.log")) {
        $log_content .= "\n" . htmlspecialchars(substr(file_get_contents("$dir/hostinger_start.log"), -1500));
    }
    
    echo "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Guasha House System</title>";
    echo "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;text-align:center;padding:40px 20px;background:#fbfaf7;color:#2c2c2c;}";
    echo ".card{max-width:550px;margin:0 auto;background:#fff;padding:30px;border-radius:16px;box-shadow:0 10px 25px rgba(0,0,0,0.06);border:1px solid #efeae2;}";
    echo ".btn{display:inline-block;margin-top:15px;padding:12px 24px;background:#c5a880;color:#fff;text-decoration:none;border-radius:8px;font-weight:600;}";
    echo ".log{text-align:left;background:#1e1e1e;color:#00ff66;padding:12px;border-radius:8px;font-size:12px;overflow-x:auto;max-height:200px;margin-top:15px;font-family:monospace;white-space:pre-wrap;}";
    echo "</style></head><body>";
    echo "<div class='card'>";
    echo "<div style='font-size:42px;margin-bottom:10px;'>🌿</div>";
    echo "<h2 style='margin:0 0 10px;color:#1a1a1a;'>กำลังเริ่มต้นระบบ Guasha House</h2>";
    echo "<p style='color:#666;font-size:14px;margin-bottom:20px;'>เซิร์ฟเวอร์กำลังเชื่อมต่อฐานข้อมูลและตั้งค่าความปลอดภัย กรุณารอสักครู่...</p>";
    echo "<a href='/?restart=1' class='btn'>🔄 รีสตาร์ทระบบ (Restart Server)</a>";
    if (!empty(trim($log_content))) {
        echo "<div class='log'><strong>System Logs:</strong>\n" . $log_content . "</div>";
    }
    echo "</div>";
    echo "<script>setTimeout(function(){ window.location.href = '/'; }, 3000);</script>";
    echo "</body></html>";
    exit;
}

$header_size = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
$http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$header_text = substr($response, 0, $header_size);
$body = substr($response, $header_size);

http_response_code($http_code);

// Forward response headers
$raw_headers = explode("\r\n", $header_text);
foreach ($raw_headers as $index => $header_line) {
    if ($index === 0 || empty(trim($header_line))) {
        continue;
    }
    $lower = strtolower($header_line);
    if (strpos($lower, 'transfer-encoding:') === false && strpos($lower, 'connection:') === false) {
        header($header_line, false);
    }
}

echo $body;
