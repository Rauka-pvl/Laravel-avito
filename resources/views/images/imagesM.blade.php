<x-app-layout>
    <x-slot name="header">
        <h2 class="font-semibold text-xl text-gray-800 dark:text-gray-200 leading-tight">
            {{ __('Добавление Много') }}
        </h2>
    </x-slot>

    <div class="py-12">
        <div class="max-w-7xl mx-auto sm:px-6 lg:px-8">
            <div class="bg-white dark:bg-gray-800 overflow-hidden shadow-sm sm:rounded-lg">
                <div class="p-6 text-gray-900 dark:text-gray-100">
                    <!-- Уведомления -->
                    <div id="alert-box" class="alert alert-warning d-none" role="alert"></div>

                    <!-- Форма для загрузки файлов -->
                    <form id="fileForm" enctype="multipart/form-data">
                        @csrf
                        <div class="mb-4">
                            <label for="folderInput" class="form-label fw-bold text-lg">Выберите файлы или
                                папку:</label>
                            <input type="file" name="files[]" id="folderInput"
                                class="form-control shadow-sm border-2 border-primary rounded" multiple
                                webkitdirectory />
                        </div>

                        <div class="text-center mb-4">
                            <button type="button" class="btn btn-gradient-primary px-5 py-2" onclick="processFiles()">
                                <i class="bi bi-file-earmark-arrow-up"></i> Обработать файлы
                            </button>
                        </div>

                        <div class="mt-5">
                            <label for="all_brand" class="form-label fw-bold text-lg">Общее название бренда для всех
                                файлов:</label>
                            <div class="input-group shadow-sm">
                                <input type="text" class="form-control border-2 border-secondary rounded"
                                    id="all_brand" placeholder="Названия бренда для всех!" />
                                <button type="button" class="btn btn-gradient-secondary px-4"
                                    onclick="all_brand_name()">
                                    <i class="bi bi-pencil-square"></i> Добавить название
                                </button>
                            </div>
                        </div>

                        <div id="files" class="mt-4"></div>

                        <div class="text-center">
                            <button type="button" class="btn btn-gradient-success px-5 py-2" id="btn-add"
                                onclick="submitForm()" style="display:none;">
                                <i class="bi bi-check-circle"></i> Добавить
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>

    <datalist id="brand_list">
        @foreach ($brands as $brand)
            <option value="{{ $brand->name }}"></option>
        @endforeach
    </datalist>

    <script>
        function processFiles() {
            const folderInput = document.getElementById('folderInput');
            const files = folderInput.files;
            const filesDiv = document.getElementById('files');

            if (files.length > 0) {
                filesDiv.innerHTML = ''; // Очистка контейнера

                for (let i = 0; i < files.length; i++) {
                    const file = files[i];

                    // Создаем контейнер для инпутов
                    const div = document.createElement('div');
                    div.classList.add('d-flex', 'align-items-center', 'mb-3', 'gap-3');
                    div.style.width = "100%"; // Контейнер на всю ширину

                    // Артикул инпут
                    const inputA = document.createElement('input');
                    inputA.type = 'text';
                    inputA.classList.add('form-control', 'shadow-sm', 'border-2', 'border-info', 'rounded');
                    inputA.placeholder = 'Артикул';
                    inputA.value = file.name;
                    inputA.style.flex = "1"; // Заставляем инпут растягиваться

                    // Бренд инпут
                    const inputB = document.createElement('input');
                    inputB.type = 'text';
                    inputB.classList.add('form-control', 'shadow-sm', 'border-2', 'border-info', 'rounded', 'brand');
                    inputB.placeholder = 'Бренд';
                    inputB.setAttribute('list', 'brand_list');
                    inputB.style.flex = "1"; // Аналогично растягиваем

                    // Добавляем инпуты в div
                    div.appendChild(inputA);
                    div.appendChild(inputB);
                    filesDiv.appendChild(div);
                }

                document.getElementById('btn-add').style.display = 'block'; // Отображаем кнопку "Добавить"
            } else {
                showAlert('Папка или файлы не выбраны. Выберите!', 'red');
            }
        }

        function all_brand_name() {
            let input = document.getElementById('all_brand').value;
            if (input) {
                document.querySelectorAll('.brand').forEach(function(element) {
                    element.value = input;
                });
            } else {
                showAlert('Поле не должно быть пустым!', 'red');
            }
        }

        function submitForm() {
            const form = document.getElementById('fileForm');
            const formData = new FormData(form);

            // Сбор данных из полей
            const filesDiv = document.getElementById('files');
            const fileInputs = filesDiv.querySelectorAll('input');

            fileInputs.forEach(input => {
                if (input.placeholder === 'Артикул') {
                    formData.append('file_names[]', input.value);
                }
                if (input.placeholder === 'Бренд') {
                    formData.append('brands[]', input.value);
                }
            });

            // Преобразование файлов в base64 и добавление в formData
            const folderInput = document.getElementById('folderInput');
            const files = folderInput.files;

            const promises = Array.from(files).map(file => {
                return new Promise((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = () => {
                        resolve(reader.result); // base64-строка
                    };
                    reader.onerror = () => reject(reader.error);
                    reader.readAsDataURL(file);
                });
            });

            // Ждём завершения всех преобразований
            Promise.all(promises).then(base64Files => {
                base64Files.forEach(base64File => {
                    formData.append('photoSrc[]', base64File);
                });

                // Отправляем данные на сервер
                fetch('{{ route('api.images.storeM') }}', {
                        method: 'POST',
                        headers: {
                            'X-CSRF-TOKEN': "{{ csrf_token() }}"
                        },
                        body: formData
                    })
                    .then(response => {
                        return response.text().then(text => {
                            if (!response.ok) {
                                // Пробуем распарсить как JSON ошибку
                                try {
                                    const err = JSON.parse(text);
                                    throw new Error(JSON.stringify(err.errors));
                                } catch (e) {
                                    // Если это не JSON (например HTML) — выводим весь текст
                                    throw new Error(text);
                                }
                            }

                            // Успешный ответ — пробуем распарсить как JSON
                            try {
                                return JSON.parse(text);
                            } catch (e) {
                                throw new Error('Ответ не является валидным JSON: ' + text);
                            }
                        });
                    })
                    .then(data => {
                        showAlert('Файлы успешно добавлены!', 'green');
                        form.reset();
                        document.getElementById('files').innerHTML = '';
                    })
                    .catch(error => {
                        console.error('Ошибка:', error);
                        showAlert(`Ошибка: ${error.message}`, 'red');
                    });
            }).catch(error => {
                console.error('Ошибка преобразования файлов:', error);
                showAlert('Ошибка преобразования файлов в Base64.', 'red');
            });
        }

        function showAlert(message, type = 'warning') {
            const alertBox = document.getElementById('alert-box');
            alertBox.className = `bg-${type}-500 text-white p-4 rounded mb-4`;
            alertBox.innerHTML = `<i class="bi bi-exclamation-triangle-fill"></i> ${message}`;
            alertBox.classList.remove('d-none');

            setTimeout(() => {
                alertBox.classList.add('d-none');
            }, 3000);
        }
    </script>

    <style>
        .btn-gradient-primary {
            background: linear-gradient(45deg, #00aaff, #0044ff);
            color: #fff;
            border: none;
            transition: all 0.3s ease-in-out;
        }

        .btn-gradient-primary:hover {
            background: linear-gradient(45deg, #0044ff, #00aaff);
            transform: scale(1.05);
        }

        .btn-gradient-success {
            background: linear-gradient(45deg, #28a745, #218838);
            color: #fff;
            border: none;
            transition: all 0.3s ease-in-out;
        }

        .btn-gradient-success:hover {
            background: linear-gradient(45deg, #218838, #28a745);
            transform: scale(1.05);
        }

        .form-control {
            font-size: 1rem;
            padding: 0.75rem;
            color: black;
        }

        .alert {
            font-size: 1.25rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
    </style>
</x-app-layout>
