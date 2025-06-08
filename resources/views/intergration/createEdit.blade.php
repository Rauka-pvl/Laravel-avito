<x-app-layout>
    <x-slot name="header">
        <h2 class="font-semibold text-xl text-gray-800 dark:text-gray-200 leading-tight">
            {{ isset($intergration) ? __('Редактирование интеграции') : __('Создание интеграции') }}
        </h2>
    </x-slot>
    <div class="py-12">
        <div class="max-w-7xl mx-auto sm:px-6 lg:px-8">
            <div class="bg-white dark:bg-gray-800 shadow sm:rounded-lg">
                <div class="p-6 text-gray-900 dark:text-gray-100">
                    <form action="{{ isset($intergration) ? route('intergration.update') : route('intergration.store') }}" method="POST">
                        @csrf
                        @if (isset($intergration))
                            @method('PUT')
                            <input type="hidden" name="id" value="{{ $intergration->id }}">
                        @endif
                        <div class="mb-4">
                            <label for="name" class="block text-sm font-medium text-gray-700 dark:text-gray-300">Название интеграции</label>
                            <input type="text" name="name" id="name" value="{{ old('name', $intergration->name ?? '') }}" required
                                   class="mt-1 block w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500" style="color: black;">
                        </div>

                        <div class="mb-4">
                            <label for="description" class="block text-sm font-medium text-gray-700 dark:text-gray-300">Описание</label>
                            <textarea name="description" id="description" rows="3"
                                      class="mt-1 block w-full border-gray-300 dark:border-gray-600 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500" style="color: black;">{{ old('description', $intergration->description ?? '') }}</textarea>
                        </div>

                        <button type="submit"
                                class="inline-flex items-center px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition duration-150 ease-in-out">
                            {{ isset($intergration) ? 'Обновить' : 'Создать' }}
                        </button>
                </div>
            </div>
        </div>
    </div>

</x-app-layout>
