@php use Illuminate\Support\Str; @endphp
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Файловый менеджер</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <script>
        function copyToClipboard(text) {
            navigator.clipboard.writeText(text).then(() => {
                alert('Путь скопирован:\n' + text);
            });
        }
    </script>
</head>
<body>
<div class="container mt-4">
    <h3>📁 Файловый менеджер: /storage/{{ $currentPath }}</h3>

    @php
        $segments = explode('/', $currentPath);
        $breadcrumb = '';
    @endphp

    <nav aria-label="breadcrumb">
        <ol class="breadcrumb">
            <li class="breadcrumb-item"><a href="{{ route('file.manager') }}">storage</a></li>
            @foreach($segments as $index => $segment)
                @if($segment)
                    @php
                        $breadcrumb .= ($index ? '/' : '') . $segment;
                    @endphp
                    <li class="breadcrumb-item">
                        <a href="{{ route('file.manager', ['path' => $breadcrumb]) }}">{{ $segment }}</a>
                    </li>
                @endif
            @endforeach
        </ol>
    </nav>

    <ul class="list-group mb-4">
        @foreach($directories as $dir)
            <li class="list-group-item">
                📁 <a href="{{ route('file.manager', ['path' => trim($currentPath . '/' . $dir, '/')]) }}">{{ $dir }}</a>
                <button class="btn btn-sm btn-outline-secondary ms-2"
                        onclick="copyToClipboard('{{ storage_path(trim($currentPath . '/' . $dir, '/')) }}')">
                    📋
                </button>
            </li>
        @endforeach
    </ul>

    <h5>📄 Файлы</h5>
    <ul class="list-group">
        @foreach($files as $file)
            @php
                $cPath = str_replace('app/public', '', $currentPath);
            @endphp
            <li class="list-group-item d-flex justify-content-between align-items-center">
                <span>{{ $file }}</span>
                <a class="btn btn-sm btn-primary" href="{{ asset('storage/' . trim($cPath . '/' . $file, '/')) }}" target="_blank">
                    Открыть
                </a>
                <button class="btn btn-sm btn-outline-secondary ms-2"
                        onclick="copyToClipboard('{{ storage_path(trim($currentPath . '/' . $dir, '/')) }}')">
                    📋
                </button>
            </li>
        @endforeach
    </ul>
</div>
</body>
</html>
