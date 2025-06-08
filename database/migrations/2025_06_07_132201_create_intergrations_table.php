<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     *
     * @return void
     */
    public function up()
    {
        Schema::create('intergrations', function (Blueprint $table) {
            $table->id();
            $table->integer('type_integration');
            $table->string('brand');
            $table->string('article');
            $table->string('description')->nullable();
            $table->string('brand_replace')->nullable();
            $table->string('article_replace')->nullable();
            $table->string('description_replace')->nullable();
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     *
     * @return void
     */
    public function down()
    {
        Schema::dropIfExists('intergrations');
    }
};
