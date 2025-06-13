<?php

namespace App\Http\Controllers;

use App\Models\Intergration;
use App\Models\TypeIntergration;
use Illuminate\Http\Request;

class IntergrationController extends Controller
{
    public function index()
    {
        $typeInters = TypeIntergration::withCount('intergrations')->get();
        // dd($typeInnter);
        return view('intergration.index', compact('typeInters'));
    }
    public function createEdit($id = null)
    {
        $intergration = null;
        if ($id) {
            $intergration = TypeIntergration::find($id);
            if (!$intergration) {
                return redirect()->route('intergration.index')->with('error', 'Интеграции не найден');
            }
        }
        return view('intergration.createEdit', compact('intergration'));
    }
    public function store(Request $request)
    {
        $data = $request->validate([
            'name' => 'required|string|max:255',
            'description' => 'nullable|string',
        ]);

        TypeIntergration::create($data);

        return redirect()->route('intergration.index')->with('success', 'Интеграции успешно создан');
    }
    public function update(Request $request)
    {
        $data = $request->validate([
            'id' => 'required|exists:type_intergrations,id',
            'name' => 'required|string|max:255',
            'description' => 'nullable|string',
        ]);

        $intergration = TypeIntergration::find($data['id']);
        $intergration->update($data);

        return redirect()->route('intergration.index')->with('success', 'Интеграции успешно обновлен');
    }
    public function destroy($id)
    {
        $intergration = TypeIntergration::find($id);
        if (!$intergration) {
            return redirect()->route('intergration.index')->with('error', 'Интеграции не найден');
        }
        $intergration->delete();

        return redirect()->route('intergration.index')->with('success', 'Интеграции успешно удален');
    }


    public function list($id)
    {
        $typeInter = TypeIntergration::find($id)->name;
        $intergration = Intergration::where('type_integration', '=', $id)->paginate(30);
        return view('intergration.list', compact('id', 'intergration', 'typeInter'));
    }
    public function listCreateEdit(Request $request, $id = null)
    {
        // $request->validate([
        //     'type_integration' => 'nullable|exists:intergrations,id',
        // ]);
        $type_integration = $request->query('type_integration');
        $intergration = null;
        if ($id) {
            $intergration = Intergration::find($id);
            $type_integration = $intergration->type_integration;
            if (!$intergration) {
                return redirect()->route('intergration.index')->with('error', 'Интеграции не найден');
            }
        }
        $typeInter = TypeIntergration::all();
        return view('intergration.list-createEdit', compact('type_integration', 'intergration', 'typeInter'));
    }
    public function listCreateM(Request $request)
    {
        // $request->validate([
        //     'type_integration' => 'nullable|exists:intergrations,id',
        // ]);
        $type_integration = $request->query('type_integration');
        return view('intergration.list-create', compact('type_integration'));
    }
    public function listStore(Request $request)
    {
        $data = $request->validate([
            'type_integration' => 'required|exists:type_intergrations,id',
            'brand' => 'required|string|max:255',
            'article' => 'required|string|max:255',
            'description' => 'nullable|string',
            'brand_replace' => 'nullable|string|max:255',
            'article_replace' => 'nullable|string|max:255',
            'description_replace' => 'nullable|string',
        ]);

        $item = Intergration::create($data);

        // Для AJAX: возвращаем данные в JSON
        return response()->json([
            'status' => 'success',
            'item' => $item,
        ]);
    }
    // public function listStore(Request $request)
    // {
    //     $data = $request->validate([
    //         'type_integration' => 'required|exists:type_intergrations,id',
    //         'brand' => 'required|string|max:255',
    //         'article' => 'required|string|max:255',
    //         'description' => 'nullable|string',
    //         'brand_replace' => 'required|string|max:255',
    //         'article_replace' => 'required|string|max:255',
    //         'description_replace' => 'nullable|string',
    //     ]);

    //     Intergration::create($data);

    //     return redirect()->route('intergration.list', $data['type_integration'])->with('success', 'Интеграции успешно создан');
    // }
    public function listCreateMultiple(Request $request)
    {
        $type_integration = $request->query('type_integration');
        return view('intergration.list-createEdit', compact('type_integration'));
    }
    public function listStoreMultiple(Request $request)
    {
        $validated = $request->validate([
            'type_integration' => 'required|exists:type_intergrations,id',
            'items' => 'required|array',
            'items.*.brand' => 'required|string|max:255',
            'items.*.article' => 'required|string|max:255',
            'items.*.description' => 'nullable|string',
            'items.*.brand_replace' => 'nullable|string|max:255',
            'items.*.article_replace' => 'nullable|string|max:255',
            'items.*.description_replace' => 'nullable|string',
        ]);

        foreach ($validated['items'] as $item) {
            Intergration::create([
                'type_integration' => $validated['type_integration'],
                ...$item,
            ]);
        }

        return redirect()->route('intergration.list', $validated['type_integration'])->with('success', 'Все записи добавлены');
    }
    public function listUpdate(Request $request, $id)
    {
        $data = $request->validate([
            'brand' => 'required|string|max:255',
            'article' => 'required|string|max:255',
            'description' => 'nullable|string',
            'brand_replace' => 'nullable|string|max:255',
            'article_replace' => 'nullable|string|max:255',
            'description_replace' => 'nullable|string',
            'type_integration' => 'required|exists:type_intergrations,id',
        ]);

        $intergration = Intergration::findOrFail($id);
        $intergration->update($data);

        return response()->json(['status' => 'success']);
    }
    // public function listUpdate(Request $request)
    // {
    //     $data = $request->validate([
    //         'id' => 'required|exists:intergrations,id',
    //         'type_integration' => 'required|exists:type_intergrations,id',
    //         'brand' => 'required|string|max:255',
    //         'article' => 'required|string|max:255',
    //         'description' => 'nullable|string',
    //         'brand_replace' => 'required|string|max:255',
    //         'article_replace' => 'required|string|max:255',
    //         'description_replace' => 'nullable|string',
    //     ]);

    //     $intergration = Intergration::find($data['id']);
    //     $intergration->update($data);

    //     return redirect()->route('intergration.list', $data['type_integration'])->with('success', 'Интеграции успешно обновлен');
    // }
    public function listDestroy($id)
    {
        $intergration = Intergration::find($id);
        if (!$intergration) {
            return redirect()->route('intergration.list')->with('error', 'Интеграции не найден');
        }
        $type_integration = $intergration->type_integration;
        $intergration->delete();

        return redirect()->route('intergration.list', $type_integration)->with('success', 'Интеграции успешно удален');
    }
}
