<?php

use App\Http\Controllers\BrandSpravController;
use App\Http\Controllers\ImagesController;
use App\Http\Controllers\IntergrationController;
use App\Http\Controllers\ProfileController;
use App\Http\Controllers\UpdateController;
use App\Jobs\UpdateXmlJob;
use Illuminate\Support\Facades\Route;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Storage;

/*
|--------------------------------------------------------------------------
| Web Routes
|--------------------------------------------------------------------------
|
| Here is where you can register web routes for your application. These
| routes are loaded by the RouteServiceProvider and all of them will
| be assigned to the "web" middleware group. Make something great!
|
*/

Route::get('/', function () {
    return view('welcome');
});

Route::get('/dashboard', function () {
    return view('dashboard');
})->middleware(['auth', 'verified'])->name('dashboard');

Route::middleware('auth')->group(function () {
    Route::get('/profile', [ProfileController::class, 'edit'])->name('profile.edit');
    Route::patch('/profile', [ProfileController::class, 'update'])->name('profile.update');
    Route::delete('/profile', [ProfileController::class, 'destroy'])->name('profile.destroy');

    Route::get('/images', [ImagesController::class, 'index'])->name('images.images');
    Route::post('/images/store', [ImagesController::class, 'store'])->name('images.store');
    Route::get('/images/create/success', function () {
        return view('create.success');
    })->name('create.success');

    Route::get('images/view', [ImagesController::class, 'view'])->name('images.view');
    Route::get('/imagesM', [ImagesController::class, 'indexM'])->name('images.imagesM');
    Route::post('/imagesM/storeM', [ImagesController::class, 'storeM'])->name('images.storeM');
    Route::get('/images/delete/{id}', [ImagesController::class, 'delete'])->name('images.delete');


    Route::get('/brand', [BrandSpravController::class, 'index'])->name('brand.index');
    Route::resource('brands', BrandSpravController::class);
    Route::delete('brands/{id}/clear', [BrandSpravController::class, 'clear'])->name('brands.clear');

    Route::get('/update', [UpdateController::class, 'index'])->name('update');
    Route::get('/update/status', [UpdateController::class, 'updateStatus'])->name('updateStatus');

    Route::get('/file-manager/{path?}', function ($path = null) {
        $relativePath = $path ? trim($path, '/') : '';
        $fullPath = storage_path($relativePath);

        if (!File::exists($fullPath) || !File::isDirectory($fullPath)) {
            abort(404, 'Папка не найдена');
        }

        $directories = File::directories($fullPath);
        $files = File::files($fullPath);

        return view('storage_view', [
            'currentPath' => $relativePath,
            'directories' => collect($directories)->map(fn($dir) => basename($dir)),
            'files' => collect($files)->map(fn($file) => basename($file)),
        ]);
    })->where('path', '.*')->name('file.manager');

    Route::get('/intergrations', [IntergrationController::class, 'index'])->name('intergration.index');
    Route::get('/intergration/create', [IntergrationController::class, 'createEdit'])->name('intergration.create');
    Route::get('/intergration/edit/{id}', [IntergrationController::class, 'createEdit'])->name('intergration.edit');
    Route::post('/intergration/store', [IntergrationController::class, 'store'])->name('intergration.store');
    Route::put('/intergration/update', [IntergrationController::class, 'update'])->name('intergration.update');
    Route::delete('/intergration/destroy/{id}', [IntergrationController::class, 'destroy'])->name('intergration.destroy');

    Route::get('/intergrations/{id}', [IntergrationController::class, 'list'])->name('intergration.list');
    Route::get('/intergration/list/create', [IntergrationController::class, 'listCreateEdit'])->name('intergration.list.create');
    Route::get('/intergration/list/edit/{id}', [IntergrationController::class, 'listCreateEdit'])->name('intergration.list.edit');
    Route::post('/intergration/list/store', [IntergrationController::class, 'listStore'])->name('intergration.list.store');
    Route::put('/intergration/list/update', [IntergrationController::class, 'listUpdate'])->name('intergration.list.update');
    Route::delete('/intergration/list/destroy/{id}', [IntergrationController::class, 'listDestroy'])->name('intergration.list.destroy');
});

Route::get('/updateXML', [UpdateController::class, 'update'])->name('updateXML');
Route::get('/updateTrast', [UpdateController::class, 'updateTrast'])->name('updateTrast');
Route::get('/products.xlsx', function () {
    $path = "/home/admin/web/233204.fornex.cloud/public_html/storage/app/public/products.xlsx;";

    if (!file_exists($path)) {
        abort(404, 'Файл не найден');
    }

    return response()->download($path);
})->name('xlsx');

Route::post('/multifinderbrands.php', [ImagesController::class, 'getOnArticul'])->name('getOnArticul');

Route::get('/phpInfo', function () {
    phpinfo();
});

require __DIR__ . '/auth.php';
