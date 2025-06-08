<x-app-layout>
    <x-slot name="header">
        <h2 class="font-semibold text-xl text-gray-800 dark:text-gray-200 leading-tight">
            {{ __('Справочник интеграции') }}
        </h2>
    </x-slot>
    <div class="py-12">
        <div class="max-w-7xl mx-auto sm:px-6 lg:px-8">
            <div class="bg-white dark:bg-gray-800 shadow sm:rounded-lg">
                <div class="p-6 text-gray-900 dark:text-gray-100">
                    <a href="{{ route('intergration.create') }}"
                        class="bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded-md text-sm transition">
                         Создать интеграцию
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
                                <th class="px-4 py-2 border">Интеграция</th>
                                <th class="px-4 py-2 border">Описание</th>
                                <th class="px-4 py-2 border">Кол-во интеграции</th>
                                <th class="px-4 py-2 border"></th>
                            </tr>
                        </thead>
                        <tbody>
                            @foreach ( $typeInters as $inter )
                                <tr>
                                    <td class="px-4 py-2 border">{{ $inter->name }}</td>
                                    <td class="px-4 py-2 border">{{ $inter->description }}</td>
                                    <td class="px-4 py-2 border">{{ $inter->intergrations_count }}</td>
                                    <td class="px-4 py-2 border flex gap-2">
                                        <a href="{{ route('intergration.list', $inter->id) }}"
                                           class="bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded-md text-sm transition">
                                            Список
                                        </a>

                                        <a href="{{ route('intergration.edit', $inter->id) }}"
                                           class="bg-yellow-500 hover:bg-yellow-600 text-white px-3 py-1 rounded-md text-sm transition">
                                            Редактировать
                                        </a>

                                        <form action="{{ route('intergration.destroy', $inter->id) }}" method="POST" onsubmit="return confirm('Вы уверены?')">
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
                    {{-- <div class="mt-4">{{ $brands->links() }}</div> --}}
                </div>
            </div>
        </div>
    </div>

</x-app-layout>
