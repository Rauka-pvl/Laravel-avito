<?php

return [
    'accepted'             => 'Поле :attribute должно быть принято.',
    'active_url'           => 'Поле :attribute не является действительным URL.',
    'after'                => 'Поле :attribute должно быть датой после :date.',
    'alpha'                => 'Поле :attribute должно содержать только буквы.',
    'alpha_dash'           => 'Поле :attribute может содержать только буквы, цифры и дефисы.',
    'alpha_num'            => 'Поле :attribute должно содержать только буквы и цифры.',
    'array'                => 'Поле :attribute должно быть массивом.',
    'before'               => 'Поле :attribute должно быть датой до :date.',
    'between'              => [
        'numeric' => 'Поле :attribute должно быть между :min и :max.',
        'file'    => 'Размер файла :attribute должен быть между :min и :max килобайт.',
        'string'  => 'Поле :attribute должно содержать от :min до :max символов.',
        'array'   => 'Поле :attribute должно содержать от :min до :max элементов.',
    ],
    'boolean'              => 'Поле :attribute должно быть true или false.',
    'confirmed'            => 'Подтверждение для :attribute не совпадает.',
    'date'                 => 'Поле :attribute не является действительной датой.',
    'date_equals'          => 'Поле :attribute должно быть датой, равной :date.',
    'date_format'          => 'Поле :attribute не соответствует формату :format.',
    'different'            => 'Поле :attribute и :other должны различаться.',
    'digits'               => 'Поле :attribute должно быть :digits цифр.',
    'digits_between'       => 'Поле :attribute должно быть между :min и :max цифр.',
    'dimensions'           => 'Поле :attribute имеет недопустимые размеры изображения.',
    'distinct'             => 'Поле :attribute имеет повторяющееся значение.',
    'email'                => 'Поле :attribute должно быть действительным адресом электронной почты.',
    'exists'               => 'Выбранное значение для :attribute неверно.',
    'file'                 => 'Поле :attribute должно быть файлом.',
    'filled'               => 'Поле :attribute должно быть заполнено.',
    'gt'                   => [
        'numeric' => 'Поле :attribute должно быть больше, чем :value.',
        'file'    => 'Размер файла :attribute должен быть больше :value килобайт.',
        'string'  => 'Поле :attribute должно содержать больше, чем :value символов.',
        'array'   => 'Поле :attribute должно содержать больше, чем :value элементов.',
    ],
    'gte'                  => [
        'numeric' => 'Поле :attribute должно быть больше или равно :value.',
        'file'    => 'Размер файла :attribute должен быть больше или равен :value килобайт.',
        'string'  => 'Поле :attribute должно содержать :value или больше символов.',
        'array'   => 'Поле :attribute должно содержать :value или больше элементов.',
    ],
    // Другие переводы сообщений валидации...
];
