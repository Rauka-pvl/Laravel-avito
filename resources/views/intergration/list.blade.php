<x-app-layout>
    <x-slot name="header">
        <h2 class="font-semibold text-xl text-gray-800 dark:text-gray-200 leading-tight">
            {{ __('Список интеграции: ') . $typeInter }}
        </h2>
    </x-slot>
    <div class="py-12">
        <div class="max-w-7xl mx-auto sm:px-6 lg:px-8">
            <div class="bg-white dark:bg-gray-800 shadow sm:rounded-lg">
                <div class="p-6 text-gray-900 dark:text-gray-100">
                    <a href="{{ route('intergration.list.createM', ['type_integration' => $id]) }}"
                        class="bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded-md text-sm transition">
                         Добавить
                     </a>
                </div>
                <div class="p-6 text-gray-900 dark:text-gray-100">
                    @if (session('success'))
                        <div class="bg-green-500 text-white p-4 rounded mb-4">
                            {{ session('success') }}
                        </div>
                    @endif

                    @if (session('error'))
                        <div class="bg-red-500 text-white p-4 rounded mb-4">
                            {{ session('error') }}
                        </div>
                    @endif
                </div>

                <div class="p-6 text-gray-900 dark:text-gray-100">
                    <table class="table-auto w-full border-collapse text-center">
                        <thead class="bg-gray-700 text-white">
                            <tr>
                                <th class="px-4 py-2 border">Бренд</th>
                                <th class="px-4 py-2 border">Артикул</th>
                                <th class="px-4 py-2 border">Описание</th>
                                <th class="px-4 py-2 border">Бренд на замену</th>
                                <th class="px-4 py-2 border">Описание добавка</th>
                                <th class="px-4 py-2 border">Артикул на замену</th>
                                <th class="px-4 py-2 border"></th>
                            </tr>
                        </thead>
                        <tbody>
                            @foreach ($intergration as $brand)
                                <tr>
                                    <td class="px-4 py-2 border">{{ $brand->brand }}</td>
                                    <td class="px-4 py-2 border">{{ $brand->article }}</td>
                                    <td class="px-4 py-2 border">{{ $brand->description }}</td>
                                    <td class="px-4 py-2 border">{{ $brand->brand_replace }}</td>
                                    <td class="px-4 py-2 border">{{ $brand->description_replace }}</td>
                                    <td class="px-4 py-2 border">{{ $brand->article_replace }}</td>
                                    <td class="px-4 py-2 border flex gap-2">
                                        <a href="{{ route('intergration.list.edit', $brand->id) }}"
                                            class="bg-yellow-500 hover:bg-yellow-600 text-white px-3 py-1 rounded-md text-sm transition">
                                            Редактировать
                                        </a>

                                        <form action="{{ route('intergration.list.destroy', $brand->id) }}" method="POST" onsubmit="return confirm('Вы уверены?')">
                                            @csrf
                                            @method('DELETE')
                                            <button type="submit"
                                                class="bg-red-500 hover:bg-red-600 text-white px-3 py-1 rounded-md text-sm transition">
                                                Удалить
                                            </button>
                                        </form>
                                    </td>
                                </tr>
                            @endforeach
                        </tbody>
                    </table>
                    <div class="mt-4">{{ $intergration->links() }}</div>
                </div>
            </div>
        </div>
    </div>

</x-app-layout>
