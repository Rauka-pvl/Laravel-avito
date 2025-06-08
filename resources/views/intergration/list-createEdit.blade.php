<x-app-layout>
    <x-slot name="header">
        <h2 class="font-semibold text-xl text-gray-800 dark:text-gray-200 leading-tight">
            {{ isset($intergration) ? __('Редактирование списка') : __('Добавление в список интеграции') }}
        </h2>
    </x-slot>
    <div class="py-12">
        <div class="max-w-7xl mx-auto sm:px-6 lg:px-8">
            <div class="bg-white dark:bg-gray-800 shadow sm:rounded-lg">
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
                    <form method="POST" action="{{ isset($intergration) ? route('intergration.list.update') : route('intergration.list.store') }}">
                        @csrf
                        @if (isset($intergration))
                            @method('PUT')
                            <input type="hidden" name="id" value="{{ $intergration->id }}">
                        @endif
                        <input hidden name="type_integration" value="{{ $type_integration }}">

                        <div class="mb-4">
                            <label for="brand" class="block text-sm font-medium text-gray-700 dark:text-gray-300">Бренд</label>
                            <input style="color: black;" type="text" name="brand" id="brand" value="{{ old('brand', $intergration->brand ?? '') }}" required class="mt-1 block w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500">
                        </div>

                        <div class="mb-4">
                            <label for="article" class="block text-sm font-medium text-gray-700 dark:text-gray-300">Артикул</label>
                            <input style="color: black;" type="text" name="article" id="article" value="{{ old('article', $intergration->article ?? '') }}" required class="mt-1 block w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500">
                        </div>

                        <div class="mb-4">
                            <label for="description" class="block text-sm font-medium text-gray-700 dark:text-gray-300">Описание</label>
                            <textarea style="color: black;" name="description" id="description" rows="3" required class="mt-1 block w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500">{{ old('description', $intergration->description ?? '') }}</textarea>
                        </div>

                        <div class="mb-4">
                            <label for="brand_replace" class="block text-sm font-medium text-gray-700 dark:text-gray-300">Бренд на замену</label>
                            <input style="color: black;" type="text" name="brand_replace" id="brand_replace" value="{{ old('brand_replace', $intergration->brand_replace ?? '') }}" required class="mt-1 block w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500">
                        </div>

                        <div class="mb-4">
                            <label for="description_replace" class="block text-sm font-medium text-gray-700 dark:text-gray-300">Описание добавка</label>
                            <textarea style="color: black;" name="description_replace" id="description_replace" rows="3" required class="mt-1 block w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500">{{ old('description_replace', $intergration->description_replace ?? '') }}</textarea>
                        </div>
                        <div class="mb-4">
                            <label for="article_replace" class="block text-sm font-medium text-gray-700 dark:text-gray-300">Артикул на замену</label>
                            <input style="color: black;" type="text" name="article_replace" id="article_replace" value="{{ old('article_replace', $intergration->article_replace ?? '') }}" required class="mt-1 block w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500">
                        </div>
                        <div class="flex items-center justify-end mt-4">
                            <button type="submit" class="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-md text-sm transition">
                                {{ isset($intergration) ? __('Обновить') : __('Добавить') }}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>

</x-app-layout>
