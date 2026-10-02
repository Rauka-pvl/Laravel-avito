<x-app-layout>
    <x-slot name="header">
        <h2 class="font-semibold text-xl text-gray-800 dark:text-gray-200 leading-tight">
            {{ __('Просмотр') }}
        </h2>
    </x-slot>

    <div class="py-12">
        <div class="max-w-7xl mx-auto sm:px-6 lg:px-8">
            <div class="bg-white dark:bg-gray-800 overflow-hidden shadow-sm sm:rounded-lg">
                <div class="p-6 text-gray-900 dark:text-gray-100">
                    @if (session('success'))
                        <div class="bg-green-500 text-white p-4 rounded mb-4">
                            {{ session('success') }}
                        </div>
                    @endif
                    <div id="deleteM_true" class="bg-green-500 text-white p-4 rounded mb-4 hidden">
                        {{ session('success') }}
                    </div>

                    @if (session('error'))
                        <div class="bg-red-500 text-white p-4 rounded mb-4">
                            {{ session('error') }}
                        </div>
                    @endif
                    <div id="deleteM_false" class="bg-red-500 text-white p-4 rounded mb-4 hidden">
                        {{ session('error') }}
                    </div>
                    <!-- Форма фильтрации -->
                    <form method="GET" action="{{ route('images.view') }}" class="mb-4 flex gap-4 items-center">
                        <input type="text" name="brand" placeholder="Бренд" value="{{ request('brand') }}"
                            class="border text-black rounded p-2 w-1/3" style="color: black;">

                        <input type="text" name="article" placeholder="Артикул" value="{{ request('article') }}"
                            class="border text-black rounded p-2 w-1/3" style="color: black;">

                        <label class="flex items-center gap-2 text-sm whitespace-nowrap">
                            <input type="checkbox" name="cyrillic" value="1" {{ request('cyrillic') ? 'checked' : '' }}>
                            Только с кириллицей
                        </label>

                        <button type="submit" class="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded">
                            Применить
                        </button>
                    </form>

                    <!-- Таблица -->
                    <table class="w-full table-auto border-collapse border border-gray-400">
                        <thead>
                            <tr class="bg-gray-200 dark:bg-gray-700">
                                <th class="border border-gray-400 p-2">
                                    <input type="checkbox" id="select-all">
                                </th>
                                <th class="border border-gray-400 p-2">#</th>
                                <th class="border border-gray-400 p-2">Бренд</th>
                                <th class="border border-gray-400 p-2">Артикул</th>
                                <th class="border border-gray-400 p-2">Просмотр</th>
                                <th class="border border-gray-400 p-2">Удалить</th>
                            </tr>
                        </thead>
                        <tbody>
                            @forelse ($images as $image)
                                <tr>
                                    <td class="border border-gray-400 p-2 text-center">
                                        <input type="checkbox" class="select-image" name="selected[]"
                                            value="{{ $image->id }}">
                                    </td>
                                    <td class="border border-gray-400 p-2">{{ $loop->iteration }}</td>
                                    <td class="border border-gray-400 p-2">{!! preg_replace('/([А-Яа-яЁё])/u', '<span class="text-red-500 font-bold">$1</span>', e($image->brand)) !!}</td>
                                    <td class="border border-gray-400 p-2">{!! preg_replace('/([А-Яа-яЁё])/u', '<span class="text-red-500 font-bold">$1</span>', e($image->articul)) !!}</td>
                                    <td class="border border-gray-400 p-2 text-center">
                                        <button type="button"
                                            class="bg-green-500 hover:bg-green-600 text-white px-4 py-2 rounded"
                                            onclick="showViewModal('{{ Storage::url('uploads/' . $image->brand . '/' . $image->articul) }}')">
                                            Просмотр
                                        </button>
                                    </td>
                                    <td class="border border-gray-400 p-2 text-center">
                                        <button type="button"
                                            class="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded"
                                            onclick="showDeleteModal('{{ route('images.delete', $image->id) }}')">
                                            Удалить
                                        </button>
                                    </td>
                                </tr>
                            @empty
                                <tr>
                                    <td colspan="6" class="text-center p-4">Нет данных</td>
                                </tr>
                            @endforelse
                        </tbody>
                    </table>

                    <!-- Кнопка для массового удаления -->
                    <div id="mass-delete-button" class="mt-4 hidden">
                        <button onclick="deleteM()" class="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded">
                            Удалить выбранные
                        </button>
                    </div>

                    <!-- Пагинация -->
                    <div class="mt-4">
                        {{ $images->links() }}
                    </div>

                    <!-- Модалка для просмотра -->
                    <div id="view-modal"
                        class="hidden fixed inset-0 bg-black bg-opacity-80 flex items-center justify-center">
                        <div class="bg-gray-800 text-white rounded-lg shadow-lg max-w-lg w-full p-4"
                            style="max-height: 80vh; overflow-y: auto; text-align: center">
                            <img id="view-image" src="" alt="Изображение" class="w-full h-auto rounded">
                            <button class="bg-gray-500 hover:bg-gray-600 text-white px-4 py-2 rounded mt-4"
                                onclick="closeModal('view-modal')">Закрыть</button>
                        </div>
                    </div>

                    <!-- Модалка для удаления -->
                    <div id="delete-modal"
                        class="hidden fixed inset-0 bg-gray-900 bg-opacity-50 flex items-center justify-center">
                        <div class="bg-gray-800 text-white rounded-lg shadow-lg max-w-sm w-full p-6">
                            <p class="text-lg">Вы уверены, что хотите удалить?</p>
                            <div class="mt-4 flex justify-between">
                                <button id="confirm-delete-button"
                                    class="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded">
                                    Удалить
                                </button>
                                <button class="bg-gray-500 hover:bg-gray-600 text-white px-4 py-2 rounded"
                                    onclick="closeModal('delete-modal')">Отмена</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Показать модалку просмотра
        function showViewModal(imageUrl) {
            document.getElementById('view-image').src = imageUrl;
            document.getElementById('view-modal').classList.remove('hidden');
        }
        // Закрытие модалки при клике вне её содержимого
        document.querySelectorAll('[id$="-modal"]').forEach(modal => {
            modal.addEventListener('click', function(event) {
                if (event.target === this) {
                    closeModal(this.id);
                }
            });
        });

        // Показать модалку удаления
        function showDeleteModal(deleteUrl) {
            const confirmButton = document.getElementById('confirm-delete-button');
            confirmButton.onclick = () => {
                window.location.href = deleteUrl;
            };
            document.getElementById('delete-modal').classList.remove('hidden');
        }

        // Закрыть модалку
        function closeModal(modalId) {
            document.getElementById(modalId).classList.add('hidden');
        }

        // Выделить все чекбоксы
        document.getElementById('select-all').addEventListener('change', function() {
            const checkboxes = document.querySelectorAll('.select-image');
            checkboxes.forEach(checkbox => checkbox.checked = this.checked);
            toggleMassDeleteButton();
        });

        // Показать кнопку удаления при выборе
        document.querySelectorAll('.select-image').forEach(checkbox => {
            checkbox.addEventListener('change', toggleMassDeleteButton);
        });

        function toggleMassDeleteButton() {
            const selected = document.querySelectorAll('.select-image:checked').length > 0;
            document.getElementById('mass-delete-button').classList.toggle('hidden', !selected);
        }

        function deleteM() {
            const selected = document.querySelectorAll('.select-image:checked');
            let deleteM = [];
            selected.forEach(function(item, index) {
                deleteM.push(item.value);
            });
            fetch(`/api/images/deleteM`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]')
                        .getAttribute('content'),
                },
                body: JSON.stringify({
                    deleteM: deleteM,
                })
            }).then(response => response.json()).then(response => {
                if (response['success']) {
                    if (response['true'].length > 0) {
                        $('#deleteM_true').removeClass('hidden').text('Успешно удаленны ID: ' + response.true);
                        console.log($('#deleteM_true'));
                    }
                    if (response['false'].length > 0) {
                        $('#deleteM_false').removeClass('hidden').text('Не удалось удалить ID: ' + response.false);
                        console.log($('#deleteM_false'));
                    }
                    setTimeout(() => {
                        location.reload();
                    }, 5000);
                }
            });
        }
    </script>
</x-app-layout>
