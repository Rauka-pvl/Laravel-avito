<?php

use App\Http\Controllers\BrandSpravController;
use App\Http\Controllers\ImagesController;
use App\Http\Controllers\ProfileController;
use App\Http\Controllers\UpdateController;
use App\Jobs\UpdateXmlJob;
use Illuminate\Support\Facades\Route;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\DB;
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
});

Route::get('/update1', [UpdateController::class, 'update'])->name('updateXML2');
Route::get('/updateXML', [UpdateController::class, 'update1'])->name('updateXML');

Route::get('/phpInfo', function () {
    phpinfo();
});

require __DIR__ . '/auth.php';
