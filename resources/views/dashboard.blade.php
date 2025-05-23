<x-app-layout>
    <x-slot name="header">
        <h2 class="font-semibold text-xl text-gray-800 dark:text-gray-200 leading-tight">
            {{ __('Dashboard') }}
        </h2>
    </x-slot>

    <div class="py-12">
        <div class="max-w-7xl mx-auto sm:px-6 lg:px-8">
            <div class="bg-white dark:bg-gray-800 overflow-hidden shadow-sm sm:rounded-lg">
                <div class="p-6 text-gray-900 dark:text-gray-100">
                    <h1>Добро пожаловать!</h1>

                </div>
                <div class="p-6 text-gray-900 dark:text-gray-100">
                    @if (auth()->user()->name == 'admin')
                        <div style="margin-bottom: 2em;">
                            <a href="https://233204.fornex.cloud/phpmyadmin/index.php" target="_blank"
                                class="px-6 py-3 bg-blue-500 hover:bg-blue-600 text-white font-semibold rounded-md shadow-md transition">
                                PHPMyAdmin
                            </a>
                        </div>
                        <div>
                            <a href="{{ route('file.manager', 'app/public/output') }}" target="_blank"
                                class="px-6 py-3 bg-blue-500 hover:bg-blue-600 text-white font-semibold rounded-md shadow-md transition">
                                File Manager
                            </a>
                        </div>
                    @endif
                </div>
            </div>
        </div>
    </div>
</x-app-layout>
