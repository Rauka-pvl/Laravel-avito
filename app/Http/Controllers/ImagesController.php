<?php

namespace App\Http\Controllers;

use App\Models\BrandSprav;
use App\Models\Image;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Exception;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;
use Illuminate\Support\Facades\Log;

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
        $json = json_decode($request->getContent());
        $json = is_array($json) ? ($json[0] ?? null) : $json;

        if (!$json || empty($json->brand) || !isset($json->article) || $json->article === '') {
            return response()->json(['error' => 'Неверный формат запроса'], 400);
        }

        $brands = $this->getMatchingBrands($json->brand);
        $normalizedArticle = $this->normalizeArticle($json->article);

        $placeholders = implode(',', array_fill(0, count($brands), '?'));
        $result = DB::select(
            "SELECT * FROM images
             WHERE LOWER(brand) IN ($placeholders)
             AND LOWER(articul) LIKE LOWER(?)
             ORDER BY articul",
            array_merge($brands, [$normalizedArticle . '%'])
        );

        $data = [];
        $baseUrl = $request->getSchemeAndHttpHost();

        foreach ($result as $row) {
            if (!$this->isImageFile($row->articul)) {
                continue;
            }

            $relativePath = 'uploads/' . strtolower($row->brand) . '/' . $row->articul;

            if (!Storage::disk('public')->exists($relativePath)) {
                continue;
            }

            if (@getimagesize(storage_path('app/public/' . $relativePath)) === false) {
                continue;
            }

            $url = $baseUrl . '/storage/' . $relativePath;
            $data[] = ['url' => str_replace(' ', '%20', $url)];
        }

        if (!empty($data)) {
            return response()->json($data);
        }

        if (!empty($result)) {
            return response()->json(['error' => 'Изображение не найдено'], 404);
        }

        return response()->json(['error' => 'Изображение не найдено!'], 404);
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
        $articul = $this->normalizeArticle($request->input('articul'));
        $uploadDirectory = 'public/uploads/' . $brand . '/';

        // Перебор загруженных файлов
        foreach ($request->file('images') as $key => $image) {
            $extension = strtolower($image->getClientOriginalExtension());
            $filename = $key === 0
                ? $articul . '.' . $extension
                : $articul . '_' . $key . '.' . $extension;

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
                $articul = $this->normalizeUploadedFileName($fileName);

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

            Log::error('Ошибка в storeM: ' . $e->getMessage(), [
                'file' => $e->getFile(),
                'line' => $e->getLine(),
                'trace' => $e->getTraceAsString(),
            ]);

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

    private function normalizeArticle(string $article): string
    {
        $article = strtolower(trim($article));
        $article = preg_replace('/[-\s]+/', '', $article);
        $article = preg_replace('/\.(jpe?g|png|gif|svg|webp)$/i', '', $article);

        return $article;
    }

    private function normalizeUploadedFileName(string $fileName): string
    {
        $fileName = strtolower(trim($fileName));
        $fileName = preg_replace('/[-\s]+/', '', $fileName);

        if (!preg_match('/\.(jpe?g|png|gif|svg|webp)$/i', $fileName)) {
            $fileName .= '.jpg';
        }

        return $fileName;
    }

    private function getMatchingBrands(string $brand): array
    {
        $brand = trim($brand);
        $rows = BrandSprav::whereRaw('LOWER(brand) = LOWER(?)', [$brand])
            ->orWhereRaw('LOWER(sprav) LIKE LOWER(?)', ['%' . $brand . '%'])
            ->get();

        $brands = collect([strtolower($brand)]);

        foreach ($rows as $row) {
            $brands->push(strtolower($row->brand));

            if ($row->sprav) {
                foreach (explode('|', $row->sprav) as $synonym) {
                    $synonym = strtolower(trim($synonym));
                    if ($synonym !== '') {
                        $brands->push($synonym);
                    }
                }
            }
        }

        return $brands->unique()->values()->all();
    }

    private function isImageFile(string $filename): bool
    {
        return (bool) preg_match('/\.(jpe?g|png|gif|svg|webp)$/i', $filename);
    }
}
