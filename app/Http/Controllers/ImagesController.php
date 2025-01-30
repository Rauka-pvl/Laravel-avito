<?php

namespace App\Http\Controllers;

use App\Models\BrandSprav;
use App\Models\Image;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Exception;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;
use PDO;

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
    public function getOnArticul(Request $request)
    {
        $brands = BrandSprav::select('brand')->where('brand', '=', $request->brand)->get();
        $brands = BrandSprav::where(function ($query) use ($request) {
            $query->whereRaw('LOWER(brand) = LOWER(?)', [$request->brand])
                ->orWhereRaw('LOWER(sprav) LIKE LOWER(CONCAT("% | ", ?, " | %"))', [$request->brand])
                ->orWhereRaw('LOWER(sprav) LIKE LOWER(CONCAT("%", ?, "%"))', [$request->brand])
                ->orWhereRaw('LOWER(sprav) = LOWER(?)', [$request->brand]);
        })->get();
        var_dump($brands);

        // $stmt1 = $pdo->prepare("SELECT brand FROM brand_sprav WHERE LOWER(brand) = LOWER(:brand) OR LOWER(sprav) LIKE LOWER(CONCAT('% | ',:sprav,' | %')) OR LOWER(sprav) LIKE LOWER(CONCAT('%',:sprav,'%')) OR LOWER(sprav) = LOWER(:sprav)");
        // $stmt1->bindParam(':brand', $json->brand, PDO::PARAM_STR);
        // $stmt1->bindParam(':sprav', $json->brand, PDO::PARAM_STR);
        // $stmt1->execute();
        // $sprav = $stmt1->fetch(PDO::FETCH_COLUMN);
        // if ($sprav) {
        //     $brand = $sprav;
        // } else {
        //     $brand = $json->brand;
        // }

        // $sql = "SELECT * FROM images WHERE LOWER(brand) = LOWER(:brand) AND LOWER(articul) LIKE LOWER(CONCAT(:articul, '%'))";
        // $stmt = $pdo->prepare($sql);
        // $stmt->bindParam(':brand', $brand, PDO::PARAM_STR);
        // $stmt->bindParam(':articul', $json->article, PDO::PARAM_STR);
        // $stmt->execute();
        // $result = $stmt->fetchAll();

        // $data = [];
        // if (!empty($result)) {
        //     foreach ($result as $row) {
        //         $url = "https://233204.fornex.cloud/uploads/" . strtolower($row['brand']) . "/" . strtolower($row['articul']);
        //         $url = str_replace(' ', '%20', $url);
        //         $imageInfo = getimagesize($url);
        //         if ($imageInfo !== false) {
        //             array_push($data, ["url" => $url]);
        //         }
        //     }

        //     if (!empty($data)) {
        //         return response()->json($data);
        //     } else {
        //         return response()->json(["error" => "Изображение не найдено"], 404);
        //     }
        // } else {
        //     return response()->json(["error" => "Изображение не найдено!"], 404);
        // }
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
