<?php

namespace App\Http\Controllers;

use App\Models\BrandSprav;
use App\Models\Image;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Exception;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;

use function PHPUnit\Framework\returnSelf;

class ImagesController extends Controller
{
    public function index()
    {
        return view("images.images");
    }

    public function indexM()
    {
        $brands = BrandSprav::all();
        return view("images.imagesM", compact("brands"));
    }
    public function view(Request $request)
    {
        $query = Image::query();

        // Фильтрация по бренду и артикулу
        if ($request->has('brand') && !empty($request->brand)) {
            $query->where('brand', 'like', '%' . $request->brand . '%');
        }

        if ($request->has('article') && !empty($request->article)) {
            $query->where('articul', 'like', '%' . $request->article . '%');
        }

        // Пагинация с 10 записями на странице
        $images = $query->paginate(40);

        return view('images.view', compact('images'));
    }

    public function store(Request $request)
    {
        // Валидация входящих данных
        $request->validate([
            'brand' => 'required|string|max:255',
            'articul' => 'required|string|max:255',
            'images' => 'required|array',
            'images.*' => 'image|mimes:jpeg,png,jpg,gif,svg|max:2048',
        ]);

        $brand = Str::lower(trim($request->input('brand')));
        $articul = Str::lower(preg_replace('/[-_\s]+/', '', $request->input('articul')));
        $uploadDirectory = 'public/uploads/' . $brand . '/';

        // Перебор загруженных файлов
        foreach ($request->file('images') as $key => $image) {
            $filename = $articul . ($key > 0 ? "_$key" : '') . '.' . $image->getClientOriginalExtension();

            // Путь к файлу
            $uploadPath = $uploadDirectory . $filename;

            // Если файл уже существует, удаляем его
            if (Storage::exists($uploadPath)) {
                Storage::delete($uploadPath);
            }

            // Сохраняем файл
            $image->storeAs($uploadDirectory, $filename);

            // Вставляем данные в таблицу images
            Image::updateOrCreate(
                ['articul' => $filename], // Уникальность по артикулу
                ['brand' => $brand, 'articul' => $filename]
            );
        }

        // Перенаправление с успешным сообщением
        return redirect()->route('create.success');
    }

    public function storeM(Request $request)
    {
        try {
            $request->validate([
                'file_names' => 'required|array',
                'file_names.*' => 'required|string',
                'brands' => 'required|array',
                'brands.*' => 'required|string',
                'photoSrc' => 'required|array',
                'photoSrc.*' => 'required|string',
            ]);
        } catch (\Illuminate\Validation\ValidationException $e) {
            return response()->json(['errors' => $e->errors()], 422);
        }
        // return response()->json($request->all(), 200);
        // dump($request->all());

        DB::beginTransaction();
        $arr = [];

        try {
            foreach ($request->file_names as $key => $fileName) {
                // Получаем бренд и артикул
                $brand = strtolower(trim($request->brands[$key]));
                $articul = preg_replace('/[-_\s]+/', '', $fileName);
                $articul = preg_replace('/\.(?=.*\.)/', '', $articul);
                $articul = strtolower(trim($articul));

                // Создаем директорию для бренда, если она не существует
                $uploadDirectory = "uploads/{$brand}/"; // Директория для загрузки

                // Путь для сохранения файла через Storage
                $uploadPath = $uploadDirectory . $articul;

                // Декодируем base64 строку в бинарные данные
                $base64 = explode(',', $request->photoSrc[$key]);
                $binaryData = base64_decode($base64[1]);

                // Проверка, существует ли файл в хранилище
                if (Storage::disk('public')->exists($uploadPath)) {
                    // Если файл существует, удаляем его
                    Storage::disk('public')->delete($uploadPath);
                }

                // Сохраняем файл в хранилище
                if (Storage::disk('public')->put($uploadPath, $binaryData)) {
                    // Добавляем запись в базу данных
                    $image = Image::updateOrCreate(
                        ['brand' => $brand, 'articul' => $articul],
                        ['articul' => $articul]
                    );

                    $arr[$key] = ['success' => "File processed successfully for: $brand/$articul"];
                } else {
                    $arr[$key] = ['error' => "Failed to save file: $brand/$articul"];
                }
            }

            // Фиксация транзакции
            DB::commit();
            return response()->json($arr, 200);
        } catch (Exception $e) {
            // Откат транзакции в случае ошибки
            DB::rollBack();
            return response()->json(['error' => "Error processing files: " . $e->getMessage()], 500);
        }
    }

    public function delete($id)
    {
        if ($id) {
            $image = Image::find($id);

            if ($image) {
                $filePath = 'uploads/' . $image->brand . '/' . $image->articul;
                if (Storage::disk('public')->exists($filePath)) {
                    if (Storage::disk('public')->delete($filePath)) {
                        $image->delete();
                        return redirect()->route('images.view')->with('success', 'Данные успешно удалены!');
                    } else return redirect()->route('images.view')->with('error', 'img не удалось удалить!');
                } else return redirect()->route('images.view')->with('error', 'img не найден!');
            }
            return redirect()->route('images.view')->with('error', 'Данные не найдены!');
        } else {
            return redirect()->route('images.view')->with('error', 'Данные не найдены!');
        }
    }

    public function deleteM(Request $request)
    {
        if ($request->deleteM) {
            $delete_true = [];
            $delete_false = [];
            foreach ($request->deleteM as $delete) {
                $image = Image::find($delete);
                if ($image) {
                    $filePath = 'uploads/' . $image->brand . '/' . $image->articul;
                    if (Storage::disk('public')->exists($filePath)) {
                        if (Storage::disk('public')->delete($filePath)) {
                            $image->delete();
                            array_push($delete_true, $delete);
                        } else array_push($delete_false, $delete);
                    } else array_push($delete_false, $delete);
                } else {
                    array_push($delete_false, $delete);
                }
            }
            return response()->json(['success' => true, 'true' => $delete_true, 'false' => $delete_false]);
        } else {
            return response()->json(['success' => false, 'false' => 'Ничего не выбрано!']);
        }
    }
}
