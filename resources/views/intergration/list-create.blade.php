<x-app-layout>
    <x-slot name="header">
        <h2 class="font-semibold text-xl text-gray-800 dark:text-gray-200 leading-tight">
            {{ __('Добавление в список интеграции') }}
        </h2>
    </x-slot>
    <div class="py-12">
        <div class="max-w-7xl mx-auto sm:px-6 lg:px-8">
            <div class="bg-white dark:bg-gray-800 shadow sm:rounded-lg">
                <div class="p-6 text-gray-900 dark:text-gray-100">
                    <form method="POST" action="{{ route('intergration.list.storeMultiple') }}">
                        @csrf
                        <input type="hidden" name="type_integration" value="{{ $type_integration }}">

                        <div id="items-wrapper">
                            <div class="item-group mb-6 border-b border-gray-500 pb-4">
                                @include('intergration.partials.fields', ['index' => 0])
                            </div>
                        </div>

                        <button type="button" onclick="addItem()" class="mb-4 bg-green-500 text-white px-4 py-2 rounded">+ Добавить ещё</button>

                        <div class="flex justify-end">
                            <button type="submit" class="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded">
                                Сохранить все
                            </button>
                        </div>
                    </form>

                    <script>
                        let index = 1;
                        function addItem() {
                            fetch(`/intergration/item-fields/${index}`)
                                .then(res => res.text())
                                .then(html => {
                                    const wrapper = document.getElementById('items-wrapper');
                                    const div = document.createElement('div');
                                    div.classList.add('item-group', 'mb-6', 'border-b', 'border-gray-500', 'pb-4');
                                    div.innerHTML = html;
                                    wrapper.appendChild(div);
                                    index++;
                                });
                        }
                    </script>
                </div>
            </div>
        </div>
    </div>

</x-app-layout>
