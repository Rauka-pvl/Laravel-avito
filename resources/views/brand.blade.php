<x-app-layout>
    <x-slot name="header">
        <h2 class="font-semibold text-xl text-gray-800 dark:text-gray-200 leading-tight">
            {{ __('Справочник Бренда') }}
        </h2>
    </x-slot>

    <div class="py-12">
        <div class="max-w-7xl mx-auto sm:px-6 lg:px-8">
            <div class="bg-white dark:bg-gray-800 shadow sm:rounded-lg">
                <div class="p-6 text-gray-900 dark:text-gray-100">
                    <!-- Форма поиска -->
                    <form method="GET" action="{{ route('brand.index') }}" class="mb-4 flex gap-4 items-center">
                        <input type="text" name="search" placeholder="Бренд" value="{{ request('search') }}"
                            class="border text-black rounded p-2 w-1/3" style="color: black;">

                        <label class="flex items-center gap-2 text-sm whitespace-nowrap">
                            <input type="checkbox" name="cyrillic" value="1" {{ request('cyrillic') ? 'checked' : '' }}>
                            Только с кириллицей
                        </label>

                        <button type="submit" class="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded">
                            Применить
                        </button>
                    </form>

                    <table class="table-auto w-full border-collapse text-center">
                        <thead class="bg-gray-700 text-white">
                            <tr>
                                <th class="px-4 py-2 border">Бренд</th>
                                <th class="px-4 py-2 border">Действие</th>
                            </tr>
                        </thead>
                        <tbody>
                            @foreach ($brands as $brand)
                                <tr class="border-t">
                                    <td class="px-4 py-2">{!! preg_replace('/([А-Яа-яЁё])/u', '<span class="text-red-500 font-bold">$1</span>', e($brand->brand)) !!}</td>
                                    <td class="px-4 py-2 space-x-2">
                                        <button onclick="openModal('view', '{{ $brand->brand }}')"
                                            class="bg-blue-500 hover:bg-blue-600 text-white py-1 px-3 rounded">
                                            Просмотр
                                        </button>
                                        <button onclick="openModal('edit', '{{ $brand->brand }}')"
                                            class="bg-yellow-500 hover:bg-yellow-600 text-white py-1 px-3 rounded">
                                            Редактировать
                                        </button>
                                        <button onclick="openModal('clear', '{{ $brand->brand }}')"
                                            class="bg-red-500 hover:bg-red-600 text-white py-1 px-3 rounded">
                                            Очистить
                                        </button>
                                    </td>
                                </tr>
                            @endforeach
                        </tbody>
                    </table>
                    <div class="mt-4">{{ $brands->links() }}</div>
                </div>
            </div>
        </div>
    </div>

    <!-- Модальное окно -->
    <div id="modal" class="fixed inset-0 flex justify-center items-center bg-black bg-opacity-70 hidden z-50">
        <div class="bg-gray-900 text-white rounded-lg w-11/12 max-w-lg p-6" onclick="event.stopPropagation()">
            <div id="loader" class="flex justify-center my-4 hidden">
                <div class="w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
            </div>
            <div id="modalContent"></div>
            <div id="m-footer" class="flex justify-end space-x-2 mt-4">
                <button onclick="closeModal()" class="bg-gray-600 hover:bg-gray-500 text-white py-1 px-4 rounded">
                    Закрыть
                </button>
            </div>
        </div>
    </div>

    <script>
        function openModal(action, brand) {
            $('#editBtn').remove();
            const modal = document.getElementById('modal');
            const loader = document.getElementById('loader');
            const content = document.getElementById('modalContent');

            loader.classList.remove('hidden');
            content.innerHTML = '';
            modal.classList.remove('hidden');

            fetch(`/api/brands/view/${brand}`)
                .then(response => response.json())
                .then(data => {
                    loader.classList.add('hidden');
                    if (data.error == 404) {
                        if (action == 'view') {
                            content.innerHTML = `<h3 class="text-lg font-bold">Информация: ${brand}</h3>
                            <p class="mt-2">Пусто!</p>`;
                        } else if (action === 'edit') {
                            content.innerHTML += `<h3 class="text-lg font-bold">Редактирования: ${brand}</h3>
                            ${renderEditForm(brand,[], true)}`;
                        } else if (action == 'clear') {
                            content.innerHTML += `<h3 class="text-lg font-bold">Очистить: ${brand}</h3>
                            <p class="mt-2">Нечего очищать!</p>`;
                        }
                    } else {
                        if (action === 'view') {
                            content.innerHTML = `<h3 class="text-lg font-bold">Информация: ${brand}</h3>
                                <p class="mt-2">${data.sprav}</p>`;
                        } else if (action === 'edit') {
                            const values = data.sprav.split(' | ');
                            content.innerHTML = `<h3 class="text-lg font-bold">Редактировать: ${brand}</h3>
                                ${renderEditForm(brand,values, false)}`;
                        } else if (action === 'clear') {
                            content.innerHTML = `<h3 class="text-lg font-bold">Очистить: ${brand}</h3>
                                <p class="mt-2">Вы точно хотите очистить?</p>
                                <button onclick="clearBrand('${brand}')" class="bg-red-500 hover:bg-red-600 text-white py-1 px-4 rounded mt-4">
                                    Очистить
                                </button>`;
                        }
                    }
                })
                .catch(error => {
                    console.error('Ошибка:', error);
                    content.innerHTML = '<p class="text-red-500">Ошибка загрузки данных.</p>';
                    loader.classList.add('hidden');
                });
        }

        function renderEditForm(brand, values, isEmpty) {
            let html = '<div class="space-y-2">';
            if (isEmpty) {
                html += createInput('');
            } else {
                values.forEach(value => {
                    html += createInput(value);
                });
            }
            html += '</div>';
            html += `<button onclick="addField()" class="bg-green-500 hover:bg-green-600 text-white py-1 px-4 rounded mt-4">
                        Добавить поле
                     </button>`;
            let m_footer = $('#m-footer');
            let save_btn = `<button id="editBtn" onclick="editBrand('${brand}')" class="bg-green-600 hover:bg-green-500 text-white py-1 px-4 rounded">
                                Сохранить
                            </button>`;
            m_footer.prepend(save_btn);
            return html;
        }

        function createInput(value) {
            return `<div class="flex items-center space-x-2">
                        <input type="text" id="brand" value="${value}" class="flex-1 p-2 bg-gray-800 text-white rounded">
                        <button onclick="removeField(this)" class="text-red-500 hover:text-red-700">&times;</button>
                    </div>`;
        }

        function addField() {
            const container = document.querySelector('#modalContent .space-y-2');
            container.insertAdjacentHTML('beforeend', createInput(''));
        }

        function removeField(button) {
            button.parentElement.remove();
        }

        function closeModal() {
            document.getElementById('modal').classList.add('hidden');
        }

        function editBrand(brand) {
            const spravElements = document.querySelectorAll('#brand');
            const spravValues = Array.from(spravElements).map(element => element.value);
            const sprav = spravValues.join(' | ');

            // Отправляем запрос
            fetch('/api/brands/edit/' + brand, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-TOKEN': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                    },
                    body: JSON.stringify({
                        brand: brand,
                        sprav: sprav
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert('Данные успешно обновлены!');
                        location.reload();
                    } else {
                        alert('Произошла ошибка: ' + data.message);
                    }
                })
                .catch(error => {
                    console.error('Ошибка:', error);
                    alert('Произошла ошибка при отправке запроса.');
                });
        }

        function clearBrand(brand) {
            // Отправка запроса очистки
            console.log('Очистка данных для бренда:', brand);
            const url = `/api/brands/clear/${brand}`;

            fetch(url, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    }
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`Ошибка: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    console.log('Ответ от сервера:', data);
                    location.reload();
                })
                .catch(error => {
                    console.error('Ошибка запроса:', error);
                    alert('Произошла ошибка при выполнении запроса.');
                });
        }
    </script>
</x-app-layout>
