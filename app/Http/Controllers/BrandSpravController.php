<?php

namespace App\Http\Controllers;

use App\Models\BrandSprav;
use App\Models\Image;
use Illuminate\Http\Request;

class BrandSpravController extends Controller
{
    public function index(Request $request)
    {
        $query = Image::select('brand')->distinct('brand');

        // Поиск по названию бренда
        if ($request->filled('search')) {
            $query->where('brand', 'like', '%' . $request->search . '%');
        }

        // Только бренды с кириллицей (включая справочник синонимов brand_sprav)
        if ($request->boolean('cyrillic')) {
            $spravBrands = BrandSprav::whereRaw("brand REGEXP '[А-Яа-яЁё]' OR sprav REGEXP '[А-Яа-яЁё]'")
                ->select('brand');
            $query->where(function ($q) use ($spravBrands) {
                $q->whereRaw("brand REGEXP '[А-Яа-яЁё]'")
                    ->orWhereIn('brand', $spravBrands);
            });
        }

        $brands = $query->paginate(30)->appends($request->query());
        return view("brand", compact("brands"));
    }
    public function view($brand)
    {
        $brand = BrandSprav::where('brand', '=', $brand)->first();
        if ($brand) {
            return response()->json($brand);
        }
        return response()->json(['error' => 404], 200);
    }
    public function AddOrEdit(Request $request)
    {
        $brand = BrandSprav::updateOrCreate(
            ['brand' => $request->brand],
            [
                'brand' => $request->brand,
                'sprav' => $request->sprav
            ]
        );
        if ($brand) {
            return response()->json(['success' => true]);
        } else {
            return response()->json(['success' => false, 'message' => 'Не удалось создать или обновить запись'], 500);
        }
    }
    public function clear($brand)
    {
        $brand = BrandSprav::where('brand', '=', $brand)->first();
        if ($brand) {
            $brand->delete();
            return response()->json(['success' => true]);
        }
        return response()->json(['success' => false, 'error' => 404]);
    }
}
