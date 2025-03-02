<?php

namespace App\Http\Controllers;

use App\Models\BrandSprav;
use App\Models\Config;
use App\Models\Update;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Storage;

class UpdateController extends Controller
{

    public function index()
    {
        $statusXML = Config::where( 'name', '=', 'xml_update_status')->first();
        $statusYML = Config::where( 'name', '=', 'yml_update_status')->first();
        $statusXLS = Config::where( 'name', '=', 'parser_status')->first();
        $timeXML = Config::where(   'name', '=', 'xml_update_time')->first();
        $timeYML = Config::where(   'name', '=', 'yml_update_time')->first();
        $timeXLS = Config::where(   'name', '=', 'parser_update_time')->first();
        return view('update', compact('timeXML', 'timeYML', 'timeXLS', 'statusXML', 'statusYML', 'statusXLS'));
    }
    public function update1()
    {
        $pythonScript = '/home/admin/web/233204.fornex.cloud/public_html/python_modules/price_photo_update/main.py';
        $logFile = '/home/admin/web/233204.fornex.cloud/public_html/logs/update1.log';
    
        $command = "nohup setsid python3 $pythonScript > $logFile 2>&1 & echo $!";
    
        $pid = shell_exec($command);
    
        return redirect()->back()->with(['success' => "Запуск обновления цен и фотографий запущен. PID: $pid"]);
    }
    
    public function updateTrast()
    {
        $pythonScript = '/home/admin/web/233204.fornex.cloud/public_html/python_modules/price_photo_update/multi_parser.py';
        $logFile = '/home/admin/web/233204.fornex.cloud/public_html/logs/update_trast.log';
    
        $command = "nohup setsid python3 $pythonScript > $logFile 2>&1 & echo $!";
    
        $pid = shell_exec($command);
    
        return redirect()->back()->with(['success' => "Запуск обновления Trast Цен запущен. PID: $pid"]);
    }
    
    public function update()
    {
        $pythonScript = '/home/admin/web/233204.fornex.cloud/public_html/python_modules/price_photo_update/main.py';
        $logFile = '/home/admin/web/233204.fornex.cloud/public_html/logs/update.log';
    
        $command = "nohup setsid python3 $pythonScript > $logFile 2>&1 & echo $!";
    
        $pid = shell_exec($command);
    
        return redirect()->back()->with(['success' => "Запуск обновления цен и фотографий запущен. PID: $pid"]);
    }
    

    public function updateStatus()
    {
        $data[0] = Config::where('name', '=', 'xml_update_status')->first();
        $data[1] = Config::where('name', '=', 'yml_update_status')->first();
        $data[2] = Config::where('name', '=', 'xml_update_time')->first();
        $data[3] = Config::where('name', '=', 'yml_update_time')->first();
        $data[4] = Config::where('name', '=', 'parser_status')->first();
        $data[5] = Config::where('name', '=', 'parser_update_time')->first();
        return response()->json($data);
    }
}
