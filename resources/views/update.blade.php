<x-app-layout>
    <x-slot name="header">
        <h2 class="font-semibold text-xl text-gray-800 dark:text-gray-200 leading-tight">
            {{ __('Обновление файлов') }}
        </h2>
    </x-slot>

    <div class="py-12">
        <div class="max-w-7xl mx-auto sm:px-6 lg:px-8">
            <div class="bg-white dark:bg-gray-800 overflow-hidden shadow-sm sm:rounded-lg">
                <div class="p-6 text-gray-900 dark:text-gray-100">
                    <h1 class="text-2xl font-bold mb-6">Обновление файлов</h1>
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
                    <!-- Блок кнопок -->
                    <div class="flex gap-4 mb-6">
                        <a href="{{ route('updateXML') }}"
                            class="px-6 py-3 bg-blue-500 hover:bg-blue-600 text-white font-semibold rounded-md shadow-md transition">
                            Обновление XML и YML
                        </a>
                        <a href="{{ route('xlsx') }}"
                            class="px-6 py-3 bg-blue-500 hover:bg-blue-600 text-white font-semibold rounded-md shadow-md transition">
                            Скачать XLSX
                        </a>
                    </div>

                    <!-- Блок последнего обновления -->
                    <div class="mt-6">
                        <h2 class="text-xl font-semibold mb-2">Статус и Время обновление</h2>
                        <div class="bg-gray-100 dark:bg-gray-700 p-4 rounded-md shadow-md">
                            <p class="text-gray-700 dark:text-gray-300">
                                <strong>XML:</strong> <span id="xml-status">{{ $statusXML->value ?? 'Данные отсутствуют' }}</span> - <span id="xml-time">{{ $timeXML->value ?? 'Данные отсутствуют' }}</span>
                            </p>
                            <p class="text-gray-700 dark:text-gray-300">
                                <strong>YML:</strong> <span id="yml-status">{{ $statusYML->value ?? 'Данные отсутствуют' }}</span> - <span id="yml-status">{{ $timeYML->value ?? 'Данные отсутствуют' }}</span>
                            </p>
                            <p class="text-gray-700 dark:text-gray-300">
                                <strong>XLSX:</strong> <span id="xls-status">{{ $statusXLS->value ?? 'Данные отсутствуют' }}</span> - <span id="yml-status">{{ $timeXLS->value ?? 'Данные отсутствуют' }}</span>
                            </p>
                        </div>
                    </div>

                    <!-- Вывод статуса -->
                    @if (session('status'))
                        <div class="mt-4 text-green-600">
                            {{ session('status') }}
                        </div>
                    @endif
                </div>
            </div>
        </div>
    </div>
    <script>
        document.addEventListener("DOMContentLoaded", function() {
            function updateStatus() {
                fetch("{{ url('/update/status') }}")
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById("xml-status").textContent = data[0]['value'] || "Данные отсутствуют";
                        document.getElementById("yml-status").textContent = data[1]['value'] || "Данные отсутствуют";
                        document.getElementById("xls-status").textContent = data[2]['value'] || "Данные отсутствуют";
                    })
                    .catch(error => console.error("Ошибка при обновлении статуса:", error));
            }

            // Обновлять каждые 5 минут (300000 мс)
            setInterval(updateStatus, 300000);
            updateStatus(); // Вызываем сразу при загрузке страницы
        });
    </script>
</x-app-layout>
