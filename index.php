<?php
/**
 * Guasha House Safe LiteSpeed Gateway
 */

ini_set('display_errors', 0);
error_reporting(0);

$dir = __DIR__;
$backend_host = "http://127.0.0.1:8000";

// Check if Uvicorn daemon is active on port 8000
$fp = @fsockopen('127.0.0.1', 8000, $errno, $errstr, 0.05);

if ($fp) {
    fclose($fp);
    
    $request_uri = $_SERVER['REQUEST_URI'] ?? '/';
    $target_url = $backend_host . $request_uri;

    $ch = curl_init($target_url);
    $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, $method);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_HEADER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, false);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);
    curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, 2);
    curl_setopt($ch, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_1_1);

    $headers = [];
    $incoming = function_exists('getallheaders') ? getallheaders() : [];
    $has_cookie = false;
    foreach ($incoming as $name => $value) {
        $lower = strtolower($name);
        if (!in_array($lower, ['host', 'content-length', 'connection'])) {
            $headers[] = "$name: $value";
        }
        if ($lower === 'cookie') $has_cookie = true;
    }
    if (!$has_cookie && !empty($_SERVER['HTTP_COOKIE'])) {
        $headers[] = "Cookie: " . $_SERVER['HTTP_COOKIE'];
    }
    $headers[] = "Host: " . ($_SERVER['HTTP_HOST'] ?? 'guashahouse.com');
    $headers[] = "X-Real-IP: " . ($_SERVER['REMOTE_ADDR'] ?? '127.0.0.1');
    $headers[] = "X-Forwarded-For: " . ($_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'] ?? '127.0.0.1');
    $headers[] = "X-Forwarded-Proto: " . ((isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] === 'on') ? 'https' : 'http');

    if (in_array($method, ['POST', 'PUT', 'PATCH', 'DELETE'])) {
        $body = file_get_contents('php://input');
        curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
        if (!empty($_SERVER['CONTENT_TYPE'])) {
            $headers[] = "Content-Type: " . $_SERVER['CONTENT_TYPE'];
        }
    }
    curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

    $response = curl_exec($ch);
    if ($response !== false) {
        $header_size = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
        $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        $header_text = substr($response, 0, $header_size);
        $body = substr($response, $header_size);
        http_response_code($http_code);

        $raw_headers = explode("\r\n", $header_text);
        foreach ($raw_headers as $index => $header_line) {
            if ($index === 0 || empty(trim($header_line))) continue;
            $lower = strtolower($header_line);
            if (strpos($lower, 'transfer-encoding:') === false && strpos($lower, 'connection:') === false) {
                header($header_line, false);
            }
        }
        echo $body;
        exit;
    }
    curl_close($ch);
}

// If port 8000 is not yet active, show status page with instructions
header('Content-Type: text/html; charset=utf-8');
?>
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🌿 ระบบจัดการร้าน กัวซา เฮ้าส์ (Guasha House)</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #fbfaf7; color: #2d3748; padding: 40px 20px; line-height: 1.6; }
        .container { max-width: 600px; margin: 0 auto; background: #fff; border-radius: 16px; padding: 35px; box-shadow: 0 10px 30px rgba(0,0,0,0.06); border: 1px solid #ede8e1; text-align: center; }
        .logo { font-size: 48px; margin-bottom: 15px; }
        h2 { margin: 0 0 10px; color: #1a202c; font-size: 24px; font-weight: 700; }
        .status-badge { display: inline-block; background: #feebc8; color: #c05621; padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 600; margin-bottom: 20px; }
        .info-box { text-align: left; background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 20px; margin-top: 20px; font-size: 14px; }
        code { background: #edf2f7; color: #805ad5; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 13px; font-weight: bold; }
        .cmd-box { background: #1a202c; color: #68d391; padding: 12px 16px; border-radius: 8px; font-family: monospace; font-size: 13px; overflow-x: auto; margin: 10px 0; word-break: break-all; }
    </style>
</head>
<body>
<div class="container">
    <div class="logo">🌿</div>
    <h2>ระบบ กัวซา เฮ้าส์ (Guasha House)</h2>
    <div class="status-badge">⏳ เซิร์ฟเวอร์กำลังรอคำสั่ง Start</div>
    
    <p style="color: #4a5568;">ไฟล์ระบบและฐานข้อมูลได้รับการติดตั้งสมบูรณ์แล้ว พร้อมเริ่มการทำงาน 24/7</p>

    <div class="info-box">
        <strong>🚀 วิธีเปิดให้ระบบออนไลน์ 24 ชั่วโมง (เลือก 1 ข้อ):</strong><br><br>
        <strong>วิธีที่ 1: ตั้งค่า Cron Job บน Hostinger (แนะนำ - เว็บจะติดตลอดเวลา)</strong>
        <p style="margin: 5px 0 10px; color: #718096;">ไปที่ <strong>hPanel &rarr; Advanced &rarr; Cron Jobs</strong> เลือก <code>Every minute (* * * * *)</code> และใส่คำสั่ง:</p>
        <div class="cmd-box">cd /home/u713703050/domains/guashahouse.com/public_html && bash hostinger_run.sh --keepalive</div>
        
        <hr style="border: none; border-top: 1px dashed #cbd5e0; margin: 15px 0;">
        
        <strong>วิธีที่ 2: รันผ่าน SSH Terminal</strong>
        <div class="cmd-box">cd /home/u713703050/domains/guashahouse.com/public_html && bash hostinger_run.sh</div>
    </div>
</div>
</body>
</html>
