<?php

namespace App\Http\Controllers;

use App\Models\BrandSprav;
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
        $timeXML = Update::find(1);
        $timeYAML = Update::find(2);
        return view('update', compact('timeXML', 'timeYAML'));
    }
    public function update()
    {
        $handle = popen('python3 /home/admin/web/233204.fornex.cloud/public_html/python_modules/price_photo_update/main.py > /dev/null 2>&1 &', 'r');
        pclose($handle);
    }
    public function update1()
    {
        $pythonScript = '/home/admin/web/233204.fornex.cloud/public_html/python_modules/price_photo_update/main.py';

        // Формируем команду для запуска в фоне
        $command = "nohup python3 $pythonScript > /dev/null 2>&1 &";

        // Выполняем команду
        exec($command);

        // PHP-код продолжает выполняться сразу после запуска Python-скрипта
        echo "Python-скрипт запущен в фоне, выполнение PHP-кода продолжается.";
    }
}
