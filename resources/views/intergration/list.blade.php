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
                    <div id="success-message" class="hidden bg-green-500 text-white p-2 rounded mb-2 text-sm"></div>

                    <table class="table-auto w-full border-collapse text-center" id="integration-table">
                        <thead class="bg-gray-700 text-white">
                            <tr>
                                <th class="px-2 py-2 border">Бренд</th>
                                <th class="px-2 py-2 border">Артикул</th>
                                <th class="px-2 py-2 border">Описание</th>
                                <th class="px-2 py-2 border">Бренд на замену</th>
                                <th class="px-2 py-2 border">Описание добавка</th>
                                <th class="px-2 py-2 border">Артикул на замену</th>
                                <th class="px-2 py-2 border">Действия</th>
                            </tr>
                        </thead>
                        <tbody>
                            @foreach ($intergration as $brand)
                                <tr data-id="{{ $brand->id }}">
                                    <td contenteditable="true" class="editable px-2 py-1 border" data-field="brand">{{ $brand->brand }}</td>
                                    <td contenteditable="true" class="editable px-2 py-1 border" data-field="article">{{ $brand->article }}</td>
                                    <td contenteditable="true" class="editable px-2 py-1 border" data-field="description">{{ $brand->description }}</td>
                                    <td contenteditable="true" class="editable px-2 py-1 border" data-field="brand_replace">{{ $brand->brand_replace }}</td>
                                    <td contenteditable="true" class="editable px-2 py-1 border" data-field="description_replace">{{ $brand->description_replace }}</td>
                                    <td contenteditable="true" class="editable px-2 py-1 border" data-field="article_replace">{{ $brand->article_replace }}</td>
                                    <td class="px-2 py-2 border flex gap-2 justify-center">
                                        <button class="save-btn bg-green-500 hover:bg-green-600 text-white px-2 py-1 rounded-md text-sm transition hidden">Сохранить</button>
                                        <form action="{{ route('intergration.list.destroy', $brand->id) }}" method="POST" onsubmit="return confirm('Вы уверены?')">
                                            @csrf
                                            @method('DELETE')
                                            <button type="submit"
                                                class="bg-red-500 hover:bg-red-600 text-white px-2 py-1 rounded-md text-sm transition">
                                                Удалить
                                            </button>
                                        </form>
                                    </td>
                                </tr>
                            @endforeach
                            <tr id="new-row">
                                <td class="px-2 py-1 border" contenteditable="true" data-field="brand"></td>
                                <td class="px-2 py-1 border" contenteditable="true" data-field="article"></td>
                                <td class="px-2 py-1 border" contenteditable="true" data-field="description"></td>
                                <td class="px-2 py-1 border" contenteditable="true" data-field="brand_replace"></td>
                                <td class="px-2 py-1 border" contenteditable="true" data-field="description_replace"></td>
                                <td class="px-2 py-1 border" contenteditable="true" data-field="article_replace"></td>
                                <td class="px-2 py-1 border">
                                    <button id="add-btn"
                                        class="bg-green-500 hover:bg-green-600 text-white px-3 py-1 rounded-md text-sm transition">
                                        Добавить
                                    </button>
                                </td>
                            </tr>
                        </tbody>
                    </table>

                    <div class="mt-4">{{ $intergration->links() }}</div>
                </div>
            </div>
        </div>
    </div>

    {{-- JavaScript --}}
    <script>
        document.addEventListener('DOMContentLoaded', () => {
            const table = document.getElementById('integration-table');
            const successMessage = document.getElementById('success-message');

            // Появление кнопки "Сохранить" при редактировании
            table.addEventListener('input', (e) => {
                const cell = e.target.closest('.editable');
                if (cell) {
                    // Подсветка отредактированной ячейки
                    cell.classList.add('bg-gray-700');

                    const row = cell.closest('tr');
                    const saveBtn = row.querySelector('.save-btn');
                    if (saveBtn) {
                        saveBtn.classList.remove('hidden');
                    }
                }
            });

            // Сохранение данных
            table.addEventListener('click', async (e) => {
                if (e.target.classList.contains('save-btn')) {
                    const row = e.target.closest('tr');
                    const id = row.dataset.id;
                    const fields = row.querySelectorAll('.editable');

                    const data = {
                        _method: 'PUT',
                        _token: '{{ csrf_token() }}',
                        type_integration: '{{ $id }}'
                    };

                    fields.forEach(field => {
                        data[field.dataset.field] = field.textContent.trim();
                    });

                    const response = await fetch(`/intergration/list/update/${id}`, {
                        method: 'POST', // Laravel принимает PUT через POST + _method
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(data)
                    });

                    const result = await response.json();

                    if (result.status === 'success') {
                        successMessage.textContent = 'Успешно сохранено!';
                        successMessage.classList.remove('hidden');
                        setTimeout(() => successMessage.classList.add('hidden'), 2000);

                        // Скрыть кнопку и убрать подсветку после успешного сохранения
                        e.target.classList.add('hidden');
                        fields.forEach(f => f.classList.remove('bg-yellow-100'));
                    } else {
                        successMessage.textContent = 'Ошибка при сохранении';
                        successMessage.classList.remove('hidden');
                    }
                }
            });
        });
    </script>
    <script>
        document.addEventListener('DOMContentLoaded', () => {
            const table = document.getElementById('integration-table');
            const successMessage = document.getElementById('success-message');
            const newRow = document.getElementById('new-row');
            const addBtn = document.getElementById('add-btn');

            // Обработка добавления новой строки
            addBtn.addEventListener('click', async () => {
                const fields = newRow.querySelectorAll('[data-field]');
                const data = {
                    _token: '{{ csrf_token() }}',
                    type_integration: '{{ $id }}'
                };

                fields.forEach(field => {
                    data[field.dataset.field] = field.textContent.trim();
                });

                const response = await fetch("{{ route('intergration.list.store') }}", {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });

                const result = await response.json();

                if (result.status === 'success') {
                    successMessage.textContent = 'Успешно добавлено!';
                    successMessage.classList.remove('hidden');
                    setTimeout(() => successMessage.classList.add('hidden'), 2000);

                    // Очистка полей
                    fields.forEach(f => f.textContent = '');

                    // Добавление новой строки в таблицу (необязательно — можно просто перезагрузить таблицу)
                    const tbody = table.querySelector('tbody');
                    const newHTML = `
                        <tr data-id="${result.item.id}">
                            <td class="px-4 py-2 border editable" contenteditable="true" data-field="brand">${result.item.brand}</td>
                            <td class="px-4 py-2 border editable" contenteditable="true" data-field="article">${result.item.article}</td>
                            <td class="px-4 py-2 border editable" contenteditable="true" data-field="description">${result.item.description || ''}</td>
                            <td class="px-4 py-2 border editable" contenteditable="true" data-field="brand_replace">${result.item.brand_replace}</td>
                            <td class="px-4 py-2 border editable" contenteditable="true" data-field="description_replace">${result.item.description_replace || ''}</td>
                            <td class="px-4 py-2 border editable" contenteditable="true" data-field="article_replace">${result.item.article_replace}</td>
                            <td class="px-4 py-2 border flex gap-2 justify-center">
                                <button class="save-btn bg-green-500 hover:bg-green-600 text-white px-2 py-1 rounded-md text-sm transition hidden">Сохранить</button>
                                <form action="/intergration/list/destroy/${result.item.id}" method="POST" onsubmit="return confirm('Вы уверены?')">
                                    <input type="hidden" name="_token" value="{{ csrf_token() }}">
                                    <input type="hidden" name="_method" value="DELETE">
                                    <button type="submit" class="bg-red-500 hover:bg-red-600 text-white px-2 py-1 rounded-md text-sm transition">Удалить</button>
                                </form>
                            </td>
                        </tr>
                    `;
                    newRow.insertAdjacentHTML('beforebegin', newHTML);
                } else {
                    successMessage.textContent = 'Ошибка при добавлении';
                    successMessage.classList.remove('hidden');
                }
            });
        });
    </script>
</x-app-layout>
