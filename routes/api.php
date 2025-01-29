<?php

use App\Http\Controllers\BrandSpravController;
use App\Http\Controllers\ImagesController;
use App\Http\Controllers\UpdateController;
use App\Jobs\UpdateXmlJob;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Route;

/*
|--------------------------------------------------------------------------
| API Routes
|--------------------------------------------------------------------------
|
| Here is where you can register API routes for your application. These
| routes are loaded by the RouteServiceProvider within a group which
| is assigned the "api" middleware group. Enjoy building your API!
|
*/

Route::middleware('auth:sanctum')->get('/user', function (Request $request) {
    return $request->user();
});
Route::post('/imagesM/storeM', [ImagesController::class, 'storeM'])->name('api.images.storeM');
Route::delete('/images/deleteM', [ImagesController::class, 'deleteM'])->name('api.images.deleteM');

Route::get('/brands/view/{id}', [BrandSpravController::class, 'view'])->name('api.brand.view');
Route::post('/brands/edit/{id}', [BrandSpravController::class, 'AddOrEdit'])->name('api.brand.AddOrEdit');
Route::post('/brands/clear/{id}', [BrandSpravController::class, 'clear'])->name('api.brand.clear');
